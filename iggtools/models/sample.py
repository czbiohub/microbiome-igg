import os
from collections import defaultdict
from iggtools.params.schemas import fetch_schema_by_dbtype, samples_pool_schema, species_profile_schema
from iggtools.common.utils import InputStream, OutputStream, select_from_tsv, command, tsprint


# Executable Documentation
# Low level functions: the Target Files
def get_single_layout(sample_name, dbtype=""):
    def per_species(species_id="", contig_id=""):
        return {
            "species_summary":        f"{sample_name}/species/species_profile.tsv",
            "snps_pileup":            f"{sample_name}/snps/output/{species_id}.snps.tsv.lz4",
            "snps_summary":           f"{sample_name}/snps/output/summary.tsv",
            "genes_coverage":         f"{sample_name}/genes/output/{species_id}.genes.tsv.lz4",
            "genes_summary":          f"{sample_name}/genes/output/summary.tsv",

            "outdir":                 f"{sample_name}/{dbtype}/output",
            "tempdir":                f"{sample_name}/{dbtype}/temp",
            "dbsdir":                 f"{sample_name}/dbs",
            "dbs_tempdir":            f"{sample_name}/dbs/temp",
            "contig_file":            f"{sample_name}/dbs/temp/{species_id}",
            "centroid_file":          f"{sample_name}/dbs/temp/{species_id}/centroids.ffn",
            "genes_info_file":        f"{sample_name}/dbs/temp/{species_id}/gene_info.txt",

            "marker_genes_file":      [f"{sample_name}/dbs/phyeco.fa{ext}" for ext in ["", ".bwt", ".header", ".sa", ".sequence"]] + \
                                        [f"", f"{sample_name}/dbs/phyeco.map"],
            "local_toc":              f"{sample_name}/dbs/genomes.tsv"  

            "species_alignments_m8":  f"{sample_name}/{dbtype}/temp/alignments.m8",
            "snps_repgenomes_bam":    f"{sample_name}/{dbtype}/repgenomes.bam",
            "genes_pangenomes_bam":   f"{sample_name}/{dbtype}/pangenomes.bam",

            "species_dbs_subdir":     f"{sample_name}/dbs/temp/{species_id}",
            "species_output_subdir":  f"{sample_name}/{dbtype}/output/{species_id}",
            "species_temp_subdir":    f"{sample_name}/{dbtype}/temp/{species_id}",

            "contigs_pileup":         f"{sample_name}/snps/temp/{species_id}/snps_{contig_id}.tsv.lz4",
            "chunk_coverage":         f"{sample_name}/genes/temp/{species_id}/genes_{contig_id}.tsv.lz4",
            "marker_genes_mapping":   f"{sample_name}/genes/temp/{species_id}/marker_to_centroid.tsv",
        }
    return per_species


if False:
    assert os.path.exists(midas_outdir), f"Provided MIDAS output {midas_outdir} for {sample_name} in sample_list is invalid"
    assert os.path.exists(self.data_dir), f"Missing MIDAS {dbtype} directiory for {self.data_dir} for {sample_name}"


class Sample: # pylint: disable=too-few-public-methods
    def __init__(self, sample_name, midas_outdir, dbtype=None):
        self.sample_name = sample_name
        self.midas_outdir = midas_outdir

        self.layout = get_single_layout(sample_name, dbtype)
        self.outdir = self.get_target_layout("outdir")
        self.tempdir = self.get_target_layout("tempdir")
        self.dbsdir = self.get_target_layout("dbsdir")

    def get_target_layout(self, filename, species_id="", contig_id=""):
        if isinstance(self.layout(species_id, contig_id)[filename], list):
            local_file_lists = self.layout(species_id, contig_id)[filename]
            print(local_file_lists)
            return [ os.path.join(self.midas_outdir, fn) for fn in local_file_lists ]
        return os.path.join(self.midas_outdir, self.layout(species_id, contig_id)[filename])

    def create_output_dir(self, debug=False):
        tsprint(f"Create output directory for sample {self.sample_name}.")
        command(f"rm -rf {self.outdir}")
        command(f"mkdir -p {self.outdir}")

        if debug and os.path.exists(self.tempdir):
            tsprint(f"Reusing existing temp data in {self.tempdir} according to --debug flag.")
        else:
            tsprint(f"Create temp directory for sample {self.sample_name}.")
            command(f"rm -rf {self.tempdir}")
            command(f"mkdir -p {self.tempdir}")

    def create_dbsdir(self, debug=False):
        if debug and os.path.exists(self.dbsdir):
            tsprint(f"Reusing existing temp data in {self.dbsdir} according to --debug flag.")
        else:
            tsprint(f"Create database directory for sample {self.sample_name}.")
            command(f"rm -rf {self.dbsdir}")
            command(f"mkdir -p {self.dbsdir}")

    def create_species_subdir(self, species_ids, debug=False, dirtype=None):
        assert dirtype is not None, f"Need to specify which step the species subdir are built"

        for species_id in species_ids:
            species_subdir = self.get_target_layout(f"species_{dirtype}_subdir", species_id)
            if debug and os.path.exists(species_subdir):
                continue
            command(f"rm -rf {species_subdir}")
            command(f"mkdir -p {species_subdir}")


    def load_profile_by_dbtype(self, dbtype):
        summary_path = self.get_target_layout(f"{dbtype}_summary")
        assert os.path.exists(summary_path), f"load_profile_by_dbtype:: missing {summary_path} for {self.sample_name}"

        schema = fetch_schema_by_dbtype(dbtype)
        profile = {}
        with InputStream(summary_path) as stream:
            for info in select_from_tsv(stream, selected_columns=schema, result_structure=dict):
                profile[info["species_id"]] = info
        self.profile = profile

    def select_species(self, genome_coverage, species_list=""):
        "Return map of species_id to coverage for the species present in the sample."
        schema = fetch_schema_by_dbtype("species")
        profile = defaultdict()
        with InputStream(self.get_target_layout("species_summary")) as stream:
            for record in select_from_tsv(stream, selected_columns=schema, result_structure=dict):
                if species_list and record["species_id"] not in args.species_list.split(","):
                    continue
                if record["coverage"] >= genome_coverage:
                    profile[record["species_id"]] = record["coverage"]
        return profile

    def remove_output_dir(self):
        command(f"rm -rf {self.tempdir}", check=False)
        command(f"rm -rf {self.outdir}", check=False)

    def remove_tempdir_dir(self):
        command(f"rm -rf {self.tempdir}", check=False)
