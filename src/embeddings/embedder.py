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


print("\nLoading MedCPT Article Encoder...")

article_tokenizer = AutoTokenizer.from_pretrained(
    ARTICLE_MODEL_NAME
)

article_model = AutoModel.from_pretrained(
    ARTICLE_MODEL_NAME
)

article_model.eval()

print("Article Encoder loaded.")


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