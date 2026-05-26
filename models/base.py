from abc import ABC, abstractmethod


class BaseModel(ABC):
    @abstractmethod
    def generate(self, messages: list, max_new_tokens: int = 256) -> str:
        """messages 리스트를 받아 생성된 텍스트를 반환."""
        ...
