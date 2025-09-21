"""Hierarchical markdown chunker for docling documents."""

from docling.chunking import BaseChunk, BaseChunker, DocChunk, DocMeta
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.types import DoclingDocument as DLDocument
from docling_core.types.doc.document import (
    DocItem,
    InlineGroup,
    LevelNumber,
    ListGroup,
)
from pydantic import ConfigDict
from typing import Any, Iterator


class HierarchicalMarkdownChunker(BaseChunker):
    r"""Markdown Chunker implementation leveraging the document layout.

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
        my_doc_ser = MarkdownDocSerializer(doc=dl_doc)
        heading_by_level: dict[LevelNumber, str] = {}
        visited: set[str] = set()
        ser_res = create_ser_result()
        excluded_refs = my_doc_ser.get_excluded_refs(**kwargs)
        for item, level in dl_doc.iterate_items(with_groups=True):
            if item.self_ref in excluded_refs:
                continue
            elif (
                isinstance(item, (ListGroup, InlineGroup, DocItem))
                and item.self_ref not in visited
            ):
                ser_res = my_doc_ser.serialize(item=item, visited=visited)
            else:
                continue

            if not ser_res.text:
                continue
            if doc_items := [u.item for u in ser_res.spans]:
                c = DocChunk(
                    text=ser_res.text,
                    meta=DocMeta(
                        doc_items=doc_items,
                        headings=[heading_by_level[k] for k in sorted(heading_by_level)]
                        or None,
                        origin=dl_doc.origin,
                    ),
                )
                yield c