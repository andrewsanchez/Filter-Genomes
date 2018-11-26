import os
import attr
import pandas as pd

from Bio import Entrez


from logbook import Logger
from genbankqc import Paths
# from retrying import retry

import xml.etree.cElementTree as ET
# from xml.etree.ElementTree import ParseError


ONE_MINUTE = 60000


@attr.s
class AssemblySummary(object):
    """Read in existing file or download latest assembly summary."""
    path = attr.ib()
    url = "ftp://ftp.ncbi.nlm.nih.gov/genomes/genbank/bacteria/assembly_summary.txt"

    def __attrs_post_init__(self):
            try:
                self.df = pd.read_csv(self.path, sep="\t", index_col=0)
            except (FileNotFoundError, pd.errors.EmptyDataError):
                self.df = self.download()

    def download(self):
        df = pd.read_csv(self.url, sep="\t", index_col=0, skiprows=1)
        df.to_csv(self.path, sep="\t")
        return df


@attr.s
class BioSample(object):
    """Download and parse BioSample metadata for GenBank bacteria genomes."""
    attributes = [
        "BioSample", "geo_loc_name", "collection_date", "strain",
        "isolation_source", "host", "collected_by", "sample_type",
        "sample_name", "host_disease", "isolate", "host_health_state",
        "serovar", "env_biome", "env_feature", "ref_biomaterial",
        "env_material", "isol_growth_condt", "num_replicons",
        "sub_species", "host_age", "genotype", "host_sex", "serotype",
        "host_disease_outcome",
        ]
    root = attr.ib(default=os.getcwd())
    def __attrs_post_init__(self):
        self.paths = Paths(root=self.root, subdirs=['metadata'])
        self.paths.mkdirs()

    # @retry(stop_max_attempt_number=3, stop_max_delay=10000, wait_fixed=100)
    def _esearch(self, email='inbox.asanchez@gmail.com', db="biosample",
                 term="bacteria[orgn] AND biosample_assembly[filter]"):
        """Use NCBI's esearch to make a query"""
        Entrez.email = email
        esearch_handle = Entrez.esearch(db=db, term=term, usehistory='y')
        self.esearch_results = Entrez.read(esearch_handle)

    def _efetch(self):
        """Use NCBI's efetch to download esearch results"""
        web_env = self.esearch_results["WebEnv"]
        query_key = self.esearch_results["QueryKey"]
        count = int(self.esearch_results["Count"])
        batch_size = 10000

        self.data = []
        db_xp = 'Ids/Id/[@db="{}"]'
        # Tuples for building XPath patterns
        xp_tups = [('SRA', 'db', db_xp), ('BioSample', 'db', db_xp)]
        for attrib in self.attributes:
            xp_tups.append((attrib, 'harmonized_name',
                            'Attributes/Attribute/[@harmonized_name="{}"]'))

        def parse_record(xml):
            data = {}
            tree = ET.fromstring(xml)
            for attrib, key, xp in xp_tups:
                e = tree.find(xp.format(attrib))
                if e is not None:
                    name = e.get(key)
                    attribute = e.text
                    data[name] = attribute
            self.data.append(pd.DataFrame(data, index=[data['BioSample']]))

        for start in range(0, count, batch_size):
            end = min(count, start+batch_size)
            print("Downloading record {} to {}".format(start+1, end))
            with Entrez.efetch(db="biosample", rettype='docsum',
                               webenv=web_env, query_key=query_key,
                               retstart=start, retmax=batch_size) as handle:
                try:
                    efetch_record = Entrez.read(handle, validate=False)
                except Entrez.Parser.CorruptedXMLError:
                    continue
                    # log here
            for xml in efetch_record['DocumentSummarySet']['DocumentSummary']:
                xml = xml['SampleData']
                parse_record(xml)

    @property
    def SRA_ids(self):
        ids = self.df[self.df.SRA.notnull()].SRA.tolist()
        return ids

    def split_SRA(self):
        """Split SRA IDs into several files for better processing with epost."""
        groups = list(zip(*(iter(self.SRA_ids),) * 5000))
        for ix, group in enumerate(groups):
            out_file = os.path.join(self.paths.metadata, "SRA_Ids_{}.txt".format(ix))
            with open(out_file, 'w') as f:
                f.write('\n'.join(group))

    def SRA_runs(self):	
        file_ = os.path.join(self.paths.metadata('SRA_runs.txt'))
        df = pd.read_csv(file_, sep='\t', error_bad_lines=False, warn_bad_lines=False)
        self.df_SRA_runs = df

    def _DataFrame(self):
        self.df = pd.DataFrame(index=['BioSample'], columns=attributes)
        self.df = pd.concat(self.data)
        self.df.set_index("BioSample", inplace=True)
        self.df.to_csv(os.path.join(self.paths.metadata, "biosample.csv"), csv)

    def generate(self):
        self._esearch()
        self._efetch()
        self._DataFrame()
        self.split_SRA()


class SRA:
    def __init__(self, args):
        "docstring"
