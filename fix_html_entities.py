"""This script attempts to fix various problems found in PIM long descriptions."""

import csv
import re
import sys
from collections import defaultdict
from html import unescape
from pathlib import Path
from typing import Callable

from rich import print  # pylint: disable=redefined-builtin
from rich.text import Text
from tomlkit import load
from tomlkit.items import AoT, Table


def find_broken_entities(text: str, transformation: Table) -> set[str]:
    """Takes a string and a transformation and returns a list of uniqe strings
    that match the search pattern in the transformation."""

    patt = re.compile(transformation["search_pattern"])  # type: ignore
    found_entities: set[str] = set()
    matches = patt.findall(text)
    if not matches:
        return found_entities

    found_entities.update([x[0] for x in matches])
    return found_entities


def highlight_match(text: str, sep: str, markup: str) -> str:
    """Takes two strings, long_desc and sep.
    Looks for sep in long_desc and adds rich.markup around sep insinde long_desc.
    Then returns the new string with the markup."""

    markup = f"[{markup.strip('[]')}]"
    before, mat, after = text.partition(sep)
    if not mat:
        return text
    if sep in after:
        after = highlight_match(after, sep, markup)
    long_desc_with_highlight = before + markup + mat + markup.replace("[", "[/", 1) + after
    return long_desc_with_highlight


def encoding_is_utf_8_with_bom(in_file: Path) -> bool:
    """Takes a file path objects and returns True if the first 3 bytes in the file are EF BB BF.
    Otherwise it returns False."""

    with in_file.open("rb") as in_fb:
        magic_bytes = in_fb.read(3)
        if b"eDA" == magic_bytes:
            # we are in Excel CSV territory which encodes CSV files with UTF with BOM (byte order mark)
            # which means the first 3 bytes are \xEF \xBB \xBF = b'eDA'
            return True
    return False


def get_processing_func(post_process_str: str) -> Callable:
    """Takes a strig and returns a callable."""
    post_processing_funcs = {
        "html.unescape": unescape,
    }
    if post_process_str in post_processing_funcs:
        return post_processing_funcs[post_process_str]
    else:
        return lambda x: x


def load_transformation_rules(in_file: str | Path) -> AoT:
    """Takes a file object or a string path of a file, assumes it's toml file and loads the data.
    Returns a dict."""
    if isinstance(in_file, str):
        in_file = Path(in_file)
        with in_file.open("r", encoding="utf-8") as inf:
            rules = load(inf)
    return rules["transformations"]  # type: ignore


def apply_transformation(text: str, transformation: Table, highlight: bool = False) -> tuple[str, str]:
    """Takes a string, a transformation and a highlight bool and applies the trasformation to the string,
    highlighting the matches and the replacements if hihghlight is True.
    Returns the old text and the new text."""

    search_pattern = re.compile(transformation["search_pattern"])  # type: ignore
    replacement_pattern = transformation["replacement_pattern"]
    post_processing_func = get_processing_func(transformation["post_process"])  # type: ignore
    post_processing_exceptions = transformation["post_process_exceptions"]
    replacements = transformation["replacements"]

    # need to remove rich.markup in case the text was 'highlighed' before

    old_text = text
    old_text = Text().from_markup(text).plain
    new_text = old_text
    matches = search_pattern.findall(old_text)
    if not matches:
        return text, text
    for mat in matches:
        replacement = mat[0]
        if replacements:
            for k, v in replacements.items():  # type: ignore
                replacement = replacement.replace(k, v)
        replacement = search_pattern.sub(replacement_pattern, replacement)
        if replacement not in post_processing_exceptions:
            replacement = post_processing_func(replacement)
        if highlight:
            replacement = f"[red u bold]{replacement}[/bold u red]"
            old_text = highlight_match(old_text, mat[0], "[bold u red]")
        new_text = new_text.replace(mat[0], replacement)
        # if mat[0] == "&#8201:":
        #     print("OLD\n", text, "\n\nNEW\n", new_text)
        #     sys.exit(1)
    return old_text, new_text


def test_transformations(
    in_file: str | Path, field_name: str, transformations: AoT, which_transformations: str | list[str] = "all"
) -> None:
    """Function to test applying multiple transformations to a csv file."""

    if isinstance(in_file, str):
        in_file = Path(in_file)
    if isinstance(which_transformations, str):
        which_transformations = [which_transformations]

    encoding = "utf-8"
    if encoding_is_utf_8_with_bom(in_file):
        encoding = "utf-8-sig"
    with in_file.open("r", encoding=encoding) as inf:
        reader = csv.DictReader(inf, dialect="excel")
        for row in reader:
            long_desc = row[field_name]
            for transform in transformations:
                name = transform["name"]
                transform_name = transform["name"]
                if not should_apply_transformation(transform_name, which_transformations):
                    continue
                old_long_desc, long_desc = apply_transformation(long_desc, transform, highlight=True)
                if old_long_desc != long_desc:
                    print(f"Transformation: {name} | Product no.: {row['Product no.']} | Language: {row['Language']}")
                    print("OLD", "\n", old_long_desc)
                    print("NEW", "\n", long_desc)
                    print("\n\n")


def should_apply_transformation(transform_name: str, which_transformations: list[str]) -> bool:
    """Takes a string and a list of strings and returns True if the string is in the list
    or 'all' is in the list."""

    if transform_name in which_transformations or "all" in which_transformations:
        return True
    return False


def find_broken_entities_in_file(
    in_file: str | Path, field_name: str, transformations: AoT, which_transformations: str | list[str] = "all"
) -> dict[str, list[str]]:
    """Takes a file path or file string, a field name (str) and a transformations AoT (toml array of tables).
    Returns a dict of lists of unique strings that the transfomrations would have
    touched in the given field value of the csv."""

    if isinstance(in_file, str):
        in_file = Path(in_file)
    if isinstance(which_transformations, str):
        which_transformations = [which_transformations]

    encoding = "utf-8-sig" if encoding_is_utf_8_with_bom(in_file) else "utf-8"
    broken_entities = defaultdict(set)
    with in_file.open("r", encoding=encoding) as inf:
        reader = csv.DictReader(inf, dialect="excel")
        for row in reader:
            for transform in transformations:
                transform_name = transform["name"]
                if not should_apply_transformation(transform_name, which_transformations):
                    continue
                row_broken_entities = find_broken_entities(row[field_name], transform)
                if not row_broken_entities:
                    continue
                broken_entities[transform["name"]].update(row_broken_entities)
    return {k: sorted(list(v)) for k, v in broken_entities.items()}


def main():
    """Main entry of the program"""

    rules_file = "rules.toml"
    in_file = "products_texts_multi_language_20221109081502_v10.csv"
    field_name = "Product Long Description"
    # found_entities = find_broken_html_entities(in_file)
    which_transormations_to_apply = [
        "invalid html entities",
        # "invalid html numbered entities",
        # "fix En:yyyy standard",
        # "fix En:yyyy/An:yyyy standard",
    ]
    # which_transormations_to_apply = "all"
    transformations = load_transformation_rules(rules_file)

    test_transformations(in_file, field_name, transformations, which_transormations_to_apply)
    broken_entities = find_broken_entities_in_file(in_file, field_name, transformations, which_transormations_to_apply)
    broken_entities = {
        k: [{x: unescape(x.replace(":", ";"))} for x in v] if "invalid" in k else v for k, v in broken_entities.items()
    }
    print(broken_entities)

    # table = map_entities(found_entities)
    # pprint(table)
    sys.exit(0)
    # out_file = Path("found_entities.csv")
    # with out_file.open("w", encoding="utf-8", newline="") as outf:
    #     out_header = ["found_entities", "needs_fix"]
    #     writer = csv.writer(outf, dialect="excel")
    #     writer.writerow(out_header)
    #     writer.writerows([(x,) for x in found_entities])


if __name__ == "__main__":
    # import timeit
    # from datetime import timedelta
    # print(str(timedelta(seconds=timeit.timeit(main, number=1))))
    main()
