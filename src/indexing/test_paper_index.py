import contextlib
import io
import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))

with contextlib.redirect_stdout(io.StringIO()):
    from indexing.build_paper_index import indexed_paper_counts, paper_document
    from vector_store.chroma_store import PAPERS_COLLECTION_NAME, client, collection, passages_for_paper


class PaperDocumentTests(unittest.TestCase):

    def test_title_and_abstract_are_joined(self):
        self.assertEqual(paper_document("A title", "Abstract  text\n here"), "A title. Abstract text here")

    def test_missing_abstract_falls_back_to_title(self):
        self.assertEqual(paper_document("A title", ""), "A title")
        self.assertEqual(paper_document("", "Only abstract"), "Only abstract")


class PaperIndexTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        names = [item.name for item in client.list_collections()]
        if PAPERS_COLLECTION_NAME not in names:
            raise unittest.SkipTest("paper collection not built; run src/indexing/build_paper_index.py")
        cls.papers = client.get_collection(PAPERS_COLLECTION_NAME)

    def test_every_indexed_paper_has_one_paper_record(self):
        passage_counts = indexed_paper_counts(collection)
        self.assertEqual(self.papers.count(), len(passage_counts))
        sample = self.papers.get(ids=sorted(passage_counts)[:20], include=["metadatas"])
        for pmcid, metadata in zip(sample["ids"], sample["metadatas"]):
            self.assertEqual(metadata["n_passages"], passage_counts[pmcid])

    def test_paper_collection_uses_documented_medcpt_configuration(self):
        self.assertEqual(self.papers.metadata.get("hnsw:space"), "ip")
        metadata = self.papers.get(ids=["PMC13529361"], include=["metadatas"])["metadatas"][0]
        self.assertEqual(metadata["pooling"], "cls")
        self.assertTrue(metadata["has_abstract"])

    def test_passages_for_paper_returns_all_passages_in_order(self):
        passages = passages_for_paper("PMC13529361")
        ids = [passage["chunk_id"] for passage in passages]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), indexed_paper_counts(collection)["PMC13529361"])
        self.assertTrue(all(passage["pmcid"] == "PMC13529361" for passage in passages))


if __name__ == "__main__":
    unittest.main()
