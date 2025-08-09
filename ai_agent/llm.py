class FakeLLM:
    """A minimal synchronous LLM stub used for demos."""

    async def ainvoke(self, prompt: str):
        class Msg:
            def __init__(self, content: str):
                self.content = content
        # Very naive: echo back a simple plan
        content = "根据提供的信息，已生成初步计划。"
        return Msg(content)


def build_default_llm() -> FakeLLM:
    return FakeLLM()
