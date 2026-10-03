import pytest


@pytest.fixture
def make_tree(tmp_path):
    def make(files):
        for rel, text in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return tmp_path

    return make
