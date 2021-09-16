#!/usr/bin/env python3
import os
from iggtools.params.schemas import fetch_schema_by_dbtype, samples_pool_schema, species_profile_schema, format_data
from iggtools.common.utils import InputStream, OutputStream, select_from_tsv, command, tsprint
from iggtools.models.sample import Sample, create_local_dir
from iggtools.models.species import Species, sort_list_of_species, parse_species


def get_pool_layout(dbtype=""):
    def per_species(species_id="", chunk_id="", contig_idx=""):
        return {
            "outdir":                     f"{dbtype}",
            "outdir_by_species":          f"{dbtype}/{species_id}",

            "tempdir":                    f"temp/{dbtype}",
            "tempdir_by_species":         f"temp/{dbtype}/{species_id}",

            "midas_iggdb_dir":            f"midas_iggdb",
            "bt2_indexes_dir":            f"bt2_indexes",

            # species
            "species_prevalence":                f"species/species_prevalence.tsv",
            "species_marker_read_counts":        f"species/species_marker_read_counts.tsv",
            "species_marker_coverage":           f"species/species_marker_coverage.tsv",
            "species_median_marker_coverage":    f"species/species_marker_median_coverage.tsv",
            "species_marker_relative_abundance": f"species/species_relative_abundance.tsv",

            # snps
            "snps_summary":               f"snps/snps_summary.tsv",
            "snps_info":                  f"snps/{species_id}/{species_id}.snps_info.tsv.lz4",
            "snps_freq":                  f"snps/{species_id}/{species_id}.snps_freqs.tsv.lz4",
            "snps_depth":                 f"snps/{species_id}/{species_id}.snps_depth.tsv.lz4",
            "snps_info_by_chunk":         f"temp/{dbtype}/{species_id}/cid.{chunk_id}_snps_info.tsv.lz4",
            "snps_freq_by_chunk":         f"temp/{dbtype}/{species_id}/cid.{chunk_id}_snps_freqs.tsv.lz4",
            "snps_depth_by_chunk":        f"temp/{dbtype}/{species_id}/cid.{chunk_id}_snps_depth.tsv.lz4",
            "snps_list_of_contigs":       f"temp/{dbtype}/{species_id}/cid.{chunk_id}_list_of_contigs",

            # genes
            "genes_summary":              f"genes/genes_summary.tsv",
            "genes_reads":                f"genes/{species_id}/{species_id}.genes_reads.tsv.lz4",
            "genes_depth":                f"genes/{species_id}/{species_id}.genes_depth.tsv.lz4",
            "genes_copynum":              f"genes/{species_id}/{species_id}.genes_copynum.tsv.lz4",
            "genes_presabs":              f"genes/{species_id}/{species_id}.genes_presabs.tsv.lz4",
            "genes_reads_by_chunk":       f"temp/{dbtype}/{species_id}/cid.{chunk_id}_genes_reads.tsv.lz4",
            "genes_depth_by_chunk":       f"temp/{dbtype}/{species_id}/cid.{chunk_id}_genes_depth.tsv.lz4",
            "genes_copynum_by_chunk":     f"temp/{dbtype}/{species_id}/cid.{chunk_id}_genes_copynum.tsv.lz4",
            "genes_presabs_by_chunk":     f"temp/{dbtype}/{species_id}/cid.{chunk_id}_genes_presabs.tsv.lz4",
        }
    return per_species


class SamplePool: # pylint: disable=too-few-public-methods

    def __init__(self, samples_list, midas_outdir, dbtype=None):
        self.toc = samples_list
        self.midas_outdir = midas_outdir
        self.layout = get_pool_layout(dbtype)
        self.samples = self.init_samples(dbtype)


    def get_target_layout(self, filename, species_id="", chunk_id="", contig_idx=""):
        return os.path.join(self.midas_outdir, self.layout(species_id, chunk_id, contig_idx)[filename])


    def create_dirs(self, list_of_dirnames, debug=False, quiet=False):
        for dirname in list_of_dirnames:
            if dirname == "outdir":
                tsprint(f"Create OUTPUT directory.")
            if dirname == "tempdir":
                tsprint(f"Create TEMP directory.")
            if dirname == "dbsdir":
                tsprint(f"Create DBS directory.")
            create_local_dir(self.get_target_layout(dirname), debug, quiet)


    def create_species_subdirs(self, species_ids, dirname, debug=False, quiet=False):
        dir_to_create = self.get_target_layout(dirname)
        for species_id in species_ids:
            create_local_dir(f"{dir_to_create}/{species_id}", debug, quiet)


    def init_samples(self, dbtype):
        """ read in table-of-content: sample_name, midas_outdir """
        samples = []
        with InputStream(self.toc) as stream:
            for row in select_from_tsv(stream, selected_columns=samples_pool_schema, result_structure=dict):
                sample = Sample(row["sample_name"], row["midas_outdir"], dbtype)
                sample.load_profile_by_dbtype(dbtype) # load profile_summary into memory for easy access
                samples.append(sample)
        return samples


    def select_species(self, dbtype, args):
        """ Initialize dictionary of species given samples """
        # Parse the species list
        species_list = parse_species(args)

        # Round One: filter <sample, species>
        raw_species = {}
        for sample in self.samples:
            for record in sample.profile.values():
                species_id = record["species_id"]
                # Skip unspeficied species
                if (species_list and species_id not in species_list):
                    continue
                # Record all the dict_of_species from the profile summary
                if species_id not in raw_species:
                    raw_species[species_id] = Species(species_id)
                # Skip low-coverage <species, sample>
                if record['mean_coverage'] < args.genome_depth:
                    continue
                # Skip low prevalent <species, sample>
                if (dbtype == "snps" and record['fraction_covered'] < args.genome_coverage):
                    continue
                # Select high quality sample-species pairs
                raw_species[species_id].list_of_samples.append(sample)
                raw_species[species_id].samples_count += 1

        # Round Two: after seeing all the <species, samples> pairs,
        # filter low prevalent species based on sample_counts
        species_keep = []
        for sp in list(raw_species.values()):
            if sp.samples_count < args.sample_counts:
                continue
            sp.fetch_samples_depth() # initialize list_of_samples_depth
            species_keep.append(sp)
        # Sort the species by descending prevalence (samples_count)
        list_of_species = sort_list_of_species(species_keep)
        return {sp.id:sp for sp in list_of_species}


    def fetch_samples_names(self):
        # TODO: should be able to delete this
        return [sample.sample_name for sample in self.samples]


    def write_summary_files(self, dict_of_species, dbtype):
        """ Write snps/genes summary files for current samples pool """

        summary_file = self.get_target_layout(f"{dbtype}_summary")
        summary_header = list(fetch_schema_by_dbtype(dbtype).keys())[1:]
        with OutputStream(summary_file) as stream:
            stream.write("\t".join(["species_id", "sample_name"] + summary_header) + "\n")
            for sp in dict_of_species.values():
                for sample in sp.list_of_samples:
                    row = list(sample.profile[sp.id].values())
                    stream.write("\t".join([str(row[0]), sample.sample_name]) + "\t" + "\t".join(map(format_data, row[1:])) + "\n")


    def remove_dirs(self, list_of_dirnames):
        for dirname in list_of_dirnames:
            dirpath = self.get_target_layout(dirname)
            command(f"rm -rf {dirpath}", check=False)
