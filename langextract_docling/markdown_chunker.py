"""Hierarchical markdown chunker for docling documents."""

from typing import Any, Iterator

from docling.chunking import BaseChunk
from docling.chunking import BaseChunker
from docling.chunking import DocChunk
from docling.chunking import DocMeta
from docling_core.types import DoclingDocument as DLDocument
from pydantic import ConfigDict

from langextract_docling.provenance_serializer import ProvenanceMarkdownSerializer


class HierarchicalMarkdownChunker(BaseChunker):
  r"""Markdown Chunker implementation leveraging the document layout.

  A thin adapter over ProvenanceMarkdownSerializer's document walk: one
  chunk per serialized top-level item, so joining the chunk texts with
  "\n\n" reproduces serialize_with_provenance()'s text exactly.

  Args:
      delim (str): Delimiter to use for merging text. Defaults to "\n".
  """

  model_config = ConfigDict(arbitrary_types_allowed=True)

  def chunk(
      self,
      dl_doc: DLDocument,
      **kwargs: Any,
  ) -> Iterator[BaseChunk]:
    r"""Chunk the provided document.

    Args:
        dl_doc (DLDocument): document to chunk

    Yields:
        Iterator[Chunk]: iterator over extracted chunks
    """
    serializer = ProvenanceMarkdownSerializer(doc=dl_doc)
    for ser_res in serializer.iter_item_results(**kwargs):
      yield DocChunk(
          text=ser_res.text,
          meta=DocMeta(
              doc_items=[span.item for span in ser_res.spans],
              headings=None,
              origin=dl_doc.origin,
          ),
      )
