from transformers import AutoTokenizer, AutoModel
import torch


QUERY_MODEL_NAME = "ncbi/MedCPT-Query-Encoder"
ARTICLE_MODEL_NAME = "ncbi/MedCPT-Article-Encoder"


print("\nLoading MedCPT Query Encoder...")

query_tokenizer = AutoTokenizer.from_pretrained(
    QUERY_MODEL_NAME
)

query_model = AutoModel.from_pretrained(
    QUERY_MODEL_NAME
)

query_model.eval()

print("Query Encoder loaded.")


_article_encoder = None


def get_article_encoder():
    """
    Load the article encoder on first use; serving needs only the query encoder.
    """

    global _article_encoder

    if _article_encoder is None:

        print("\nLoading MedCPT Article Encoder...")

        tokenizer = AutoTokenizer.from_pretrained(
            ARTICLE_MODEL_NAME
        )

        model = AutoModel.from_pretrained(
            ARTICLE_MODEL_NAME
        )

        model.eval()

        print("Article Encoder loaded.")

        _article_encoder = (tokenizer, model)

    return _article_encoder


def mean_pooling(last_hidden_state, attention_mask):
    """
    Mean pooling with attention mask.
    """

    mask = attention_mask.unsqueeze(-1).expand(
        last_hidden_state.size()
    ).float()

    summed = torch.sum(
        last_hidden_state * mask,
        dim=1
    )

    counts = torch.clamp(
        mask.sum(dim=1),
        min=1e-9
    )

    return summed / counts


def embed_paper_query(text: str):
    """
    Encode a question for the paper index (CLS pooling, max_length 64, as documented for MedCPT).
    """

    inputs = query_tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=64,
        padding=True
    )

    with torch.no_grad():

        outputs = query_model(**inputs)

    return outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()


def embed_query(text: str):
    """
    Encode user question.
    """

    inputs = query_tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True
    )

    with torch.no_grad():

        outputs = query_model(**inputs)

        embedding = mean_pooling(
            outputs.last_hidden_state,
            inputs["attention_mask"]
        )

    return embedding.squeeze().cpu().numpy()


def embed_document(text: str):
    """
    Encode article chunk.
    """

    article_tokenizer, article_model = get_article_encoder()

    inputs = article_tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True
    )

    with torch.no_grad():

        outputs = article_model(**inputs)

        embedding = mean_pooling(
            outputs.last_hidden_state,
            inputs["attention_mask"]
        )

    return embedding.squeeze().cpu().numpy()


def embed_papers(papers, pooling: str = "mean", batch_size: int = 16):
    """
    Encode (title, abstract) pairs as MedCPT article inputs.
    """

    if pooling not in ("mean", "cls"):
        raise ValueError(f"Unknown pooling: {pooling}")

    article_tokenizer, article_model = get_article_encoder()

    embeddings = []

    for start in range(0, len(papers), batch_size):

        batch = [
            [title or "", abstract or ""]
            for title, abstract in papers[start:start + batch_size]
        ]

        inputs = article_tokenizer(
            batch,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        )

        with torch.no_grad():

            outputs = article_model(**inputs)

            if pooling == "cls":
                pooled = outputs.last_hidden_state[:, 0, :]
            else:
                pooled = mean_pooling(
                    outputs.last_hidden_state,
                    inputs["attention_mask"]
                )

        embeddings.extend(pooled.cpu().numpy())

    return embeddings


def embed_chunk(chunk: dict):

    text = chunk["text"].strip()

    if not text:
        return None

    embedding = embed_document(text)

    if len(embedding) == 0:
        return None

    return {
        **chunk,
        "embedding": embedding.tolist()
    }


def embed_chunks(chunks):

    embedded_chunks = []

    for chunk in chunks:

        embedded = embed_chunk(chunk)

        if embedded is not None:
            embedded_chunks.append(embedded)

    return embedded_chunks

if __name__ == "__main__":

    query_vec = embed_query(
        "What resistance mechanisms emerge after first-line osimertinib?"
    )

    doc_vec = embed_document(
        "MET amplification is a common resistance mechanism."
    )

    print(
        "\nQuery dimension:",
        len(query_vec)
    )

    print(
        "Document dimension:",
        len(doc_vec)
    )