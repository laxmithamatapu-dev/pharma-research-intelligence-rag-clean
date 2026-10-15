import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

SRC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))

with contextlib.redirect_stdout(io.StringIO()):
    import embeddings.embedder as embedder
    from vector_store.chroma_store import collection


class LazyArticleEncoderTests(unittest.TestCase):

    def test_import_does_not_load_article_encoder(self):
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "import embeddings.embedder as e; print(e._article_encoder is None)",
                str(SRC_ROOT),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip().splitlines()[-1], "True")
        self.assertNotIn("Article Encoder loaded", result.stdout)

    def test_embed_document_reproduces_stored_index_vectors(self):
        stored = collection.get(ids=["PMC13529361_0006", "PMC13600002_0015"], include=["documents", "embeddings"])
        with contextlib.redirect_stdout(io.StringIO()):
            for text, vector in zip(stored["documents"], stored["embeddings"]):
                fresh = embedder.embed_document(text.strip())
                self.assertTrue(np.allclose(fresh, np.asarray(vector), atol=1e-5))

    def test_embed_papers_supports_mean_and_cls(self):
        papers = [("Osimertinib resistance", "MET amplification emerged after progression."), ("Title only", "")]
        with contextlib.redirect_stdout(io.StringIO()):
            mean_vectors = embedder.embed_papers(papers, pooling="mean")
            cls_vectors = embedder.embed_papers(papers, pooling="cls")
        self.assertEqual(len(mean_vectors), 2)
        self.assertEqual(mean_vectors[0].shape, (768,))
        self.assertFalse(np.allclose(mean_vectors[0], cls_vectors[0]))

    def test_embed_papers_rejects_unknown_pooling(self):
        with self.assertRaises(ValueError):
            embedder.embed_papers([("t", "a")], pooling="max")


if __name__ == "__main__":
    unittest.main()
