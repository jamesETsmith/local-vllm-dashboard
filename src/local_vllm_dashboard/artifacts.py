import hashlib
from dataclasses import dataclass
from pathlib import Path

from local_vllm_dashboard.contracts import Bundle


@dataclass(frozen=True)
class ArtifactContent:
    path: str
    role: str
    media_type: str
    content: bytes


def artifact_contents(bundle: Bundle, paths: tuple[Path, ...]) -> tuple[ArtifactContent, ...]:
    available = {path.name: path for path in paths}
    contents = []
    for declaration in bundle.run.source.artifacts:
        path = available.get(Path(declaration.path).name)
        if path is None:
            raise ValueError(f"missing artifact file: {declaration.path}")
        content = path.read_bytes()
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if len(content) != declaration.size_bytes or digest != declaration.digest:
            raise ValueError(f"artifact does not match declaration: {declaration.path}")
        media_type = "application/json" if path.suffix == ".json" else "application/yaml"
        contents.append(
            ArtifactContent(
                path=declaration.path,
                role=declaration.role,
                media_type=media_type,
                content=content,
            )
        )
    return tuple(contents)
