"""Files a browser-use agent may upload: the step's explicit list + the product images."""

from agent.ec_skills.browser_node.runner import resolve_available_file_paths


def test_explicit_upload_files_of_any_type_come_first(tmp_path):
    csv_file, video = tmp_path / "listings.csv", tmp_path / "demo.mp4"
    csv_file.write_text("x")
    video.write_bytes(b"x")
    (tmp_path / "front.jpg").write_bytes(b"x")
    state = {"prompt_refs": {"upload_files": [str(csv_file), str(video), str(tmp_path / "gone.png")],
                             "product_dir": str(tmp_path)}}
    got = resolve_available_file_paths(state)
    assert got[:2] == [str(csv_file), str(video)], "missing files are skipped"
    assert got[2:] == [str(tmp_path / "front.jpg")]


def test_product_dir_alone_still_gives_only_images(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    assert resolve_available_file_paths({"prompt_refs": {"product_dir": str(tmp_path)}}) == [str(tmp_path / "a.png")]
    assert resolve_available_file_paths({}) == []
