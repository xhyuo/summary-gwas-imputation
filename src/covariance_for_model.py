__author__ = "alvaro barbeira"

import logging
import os
import re
import sqlite3
import pandas
import numpy
import gzip
from timeit import default_timer as timer

from pyarrow import parquet as pq

from genomic_tools_lib import Logging, Utilities
from genomic_tools_lib.data_management import TextFileTools
from genomic_tools_lib.miscellaneous import matrices, PandasHelpers
from genomic_tools_lib.miscellaneous import Genomics
from genomic_tools_lib.file_formats import Parquet

def get_file_map(args):
    r = re.compile(args.parquet_genotype_pattern)
    files = os.listdir(args.parquet_genotype_folder)
    files = {int(r.search(f).groups()[0]):os.path.join(args.parquet_genotype_folder, f) for f in files if r.search(f)}
    p = {}
    for k,v in files.items():
        g = pq.ParquetFile(v)
        p[k] = g
    return p

def run(args):
    if os.path.exists(args.output):
        logging.info("Output already exists, either delete it or move it")
        return

    logging.info("Getting parquet genotypes")
    file_map = get_file_map(args)

    logging.info("Getting genes")
    with sqlite3.connect(args.model_db) as connection:
        extra = pandas.read_sql("SELECT * FROM EXTRA", connection)

    logging.info("Processing")
    with gzip.open(args.output, "w") as f:
        f.write("GENE RSID1 RSID2 VALUE\n".encode())
        with sqlite3.connect(args.model_db) as connection:
            for i,t in enumerate(extra.itertuples()):
                g_ = t.gene
                logging.log(9, "Proccessing %i:%s", i, g_)
                w = pandas.read_sql("select * from weights where gene = '{}';".format(g_), connection)

                chr_ = w.varID.values[0].split("_")[0].split("chr")[1]
                dosage = file_map[int(chr_)]
                d = Parquet._read(dosage, columns=w.varID.values, skip_individuals=True)
                var_ids = list(d.keys())
                rsids = pandas.DataFrame({"varID":var_ids}).merge(w[["varID", "rsid"]], on="varID").rsid
                c = numpy.cov([d[x] for x in var_ids])
                c = matrices._flatten_matrix_data([(w.gene.values[0], rsids, c)])
                for entry in c:
                    l = "{} {} {} {}\n".format(entry[0], entry[1], entry[2], entry[3])
                    f.write(l.encode())
    logging.info("Finished building covariance.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser("Generate BSLMM runs on study")
    parser.add_argument("-parquet_genotype_folder", help="Parquet Genotype folder")
    parser.add_argument("-parquet_genotype_pattern", help="Pattern to detect parquet genotypes by chromosome")
    parser.add_argument("-model_db", help="Where to save stuff")
    parser.add_argument("-output", help="Where to save stuff")
    parser.add_argument("-parsimony", help="Log verbosity level. 1 is everything being logged. 10 is only high level messages, above 10 will hardly log anything", default = "10")

    args = parser.parse_args()

    Logging.configure_logging(int(args.parsimony))

    run(args)