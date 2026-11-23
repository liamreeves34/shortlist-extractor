"""Step 3.3: pipeline/build_dataset.py. Runs on an invented manifest; never reads data/."""

import json

import pytest

from pipeline import build_dataset
from pipeline.build_dataset import MAX_HELDOUT_ORG_SIZE, org_key, split


def manifest(sizes: dict[str, int]) -> list[dict]:
    """Invented manifest lines: `sizes` maps organization name -> number of postings."""
    lines = []
    for org, count in sizes.items():
        for n in range(count):
            lines.append(
                {
                    "hash": f"sha256:{org}-{n}",
                    "provider": "greenhouse",
                    "token": org.lower().replace(" ", ""),
                    "organization": org,
                    "external_id": str(n),
                    "fetched_at": "2026-11-15T00:00:00+00:00",
                }
            )
    return lines


@pytest.fixture
def lines():
    # 300 small organizations of 1-5 postings, plus a few big ones.
    sizes = {f"Company {i}": 1 + i % 5 for i in range(300)}
    sizes.update({"Big One": 60, "Big Two": 40, "Edge Case": MAX_HELDOUT_ORG_SIZE + 1})
    return manifest(sizes)


def orgs_in(chosen: list[dict]) -> set[str]:
    return {org_key(line["organization"]) for line in chosen}


def test_no_organization_in_two_splits(lines):
    splits = split(lines, seed=1)
    train, cal, test = (orgs_in(splits[name]) for name in ("train_pool", "calibration", "test"))
    assert not train & cal
    assert not train & test
    assert not cal & test


def test_every_posting_lands_in_exactly_one_split(lines):
    splits = split(lines, seed=1)
    hashes = [line["hash"] for chosen in splits.values() for line in chosen]
    assert sorted(hashes) == sorted(line["hash"] for line in lines)


def test_held_out_splits_are_near_their_targets(lines):
    splits = split(lines, seed=1)
    assert (
        build_dataset.CALIBRATION_SIZE - 5
        <= len(splits["calibration"])
        <= build_dataset.CALIBRATION_SIZE
    )
    assert build_dataset.TEST_SIZE - 5 <= len(splits["test"]) <= build_dataset.TEST_SIZE


def test_big_organizations_stay_in_the_train_pool(lines):
    splits = split(lines, seed=1)
    for name in ("calibration", "test"):
        assert not {"big one", "big two", "edge case"} & orgs_in(splits[name])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_same_seed_same_split(lines, seed):
    assert split(lines, seed) == split(lines, seed)


def test_input_order_does_not_matter(lines):
    assert split(lines, seed=1) == split(list(reversed(lines)), seed=1)


def test_different_seeds_give_different_splits(lines):
    assert split(lines, seed=1)["test"] != split(lines, seed=2)["test"]


def test_name_variants_are_one_organization():
    assert org_key("Acme  Robotics ") == org_key("acme robotics")
    assert org_key("Astera Labs Early Career - North America 2027") == org_key("Astera")


def test_aliased_names_stay_together():
    lines = manifest({"DRW": 2, "DRW - University Jobs": 2}) + manifest(
        {f"Filler {i}": 1 for i in range(200)}
    )
    for seed in range(20):
        splits = split(lines, seed)
        holding = [name for name, chosen in splits.items() if "drw" in orgs_in(chosen)]
        assert len(holding) == 1


def test_load_drops_repeated_hashes(tmp_path):
    path = tmp_path / "collected.jsonl"
    rows = manifest({"Acme": 2})
    path.write_text("\n".join(json.dumps(r) for r in [*rows, rows[0]]) + "\n", encoding="utf-8")
    assert len(build_dataset.load(path)) == 2


def test_write_creates_split_files_and_summary(tmp_path, lines):
    splits = split(lines, seed=7)
    build_dataset.write(splits, tmp_path, seed=7)
    for name, chosen in splits.items():
        written = (tmp_path / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(row) for row in written] == chosen
    summary = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
    assert summary["seed"] == 7
    assert summary["splits"]["test"]["postings"] == len(splits["test"])


def test_split_files_never_contain_text(tmp_path, lines):
    build_dataset.write(split(lines, seed=7), tmp_path, seed=7)
    for name in ("train_pool", "calibration", "test"):
        for row in (tmp_path / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            assert "text" not in json.loads(row)
