"""Provider implementation for docling."""

import os
import langextract as lx


@lx.providers.registry.register(r'^docling', priority=10)
class doclingLanguageModel(lx.inference.BaseLanguageModel):
    """LangExtract provider for docling.

    This provider handles model IDs matching: ['^docling']
    """

    def __init__(self, model_id: str, api_key: str = None, **kwargs):
        """Initialize the docling provider.

        Args:
            model_id: The model identifier.
            api_key: API key for authentication.
            **kwargs: Additional provider-specific parameters.
        """
        super().__init__()
        self.model_id = model_id
        self.api_key = api_key or os.environ.get('DOCLING_API_KEY')

        # self.client = YourClient(api_key=self.api_key)
        self._extra_kwargs = kwargs

    def infer(self, batch_prompts, **kwargs):
        """Run inference on a batch of prompts.

        Args:
            batch_prompts: List of prompts to process.
            **kwargs: Additional inference parameters.

        Yields:
            Lists of ScoredOutput objects, one per prompt.
        """
        for prompt in batch_prompts:
            # result = self.client.generate(prompt, **kwargs)
            result = f"Mock response for: {prompt[:50]}..."
            yield [lx.inference.ScoredOutput(score=1.0, output=result)]
