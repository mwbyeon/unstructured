import re

import pytest

from unstructured.metrics.text_extraction import calculate_edit_distance
from unstructured.partition.auto import partition


def test_calculate_edit_distance():
    source_cct = "I like pizza. I like bagels."
    source_cct_word_space = "I like p i z z a . I like bagles."
    source_cct_spaces = re.sub(r"\s+", " ", " ".join(source_cct))
    source_cct_no_space = source_cct.replace(" ", "")
    source_cct_one_sentence = "I like pizza."
    source_cct_missing_word = "I like pizza. I like ."
    source_cct_addn_char = "I like pizza. I like beagles."
    source_cct_dup_word = "I like pizza pizza. I like bagels."

    assert round(calculate_edit_distance(source_cct, source_cct, return_as="score"), 2) == 1.0
    assert (
        round(calculate_edit_distance(source_cct_word_space, source_cct, return_as="score"), 2)
        == 0.75
    )
    assert (
        round(calculate_edit_distance(source_cct_spaces, source_cct, return_as="score"), 2) == 0.39
    )
    assert (
        round(calculate_edit_distance(source_cct_no_space, source_cct, return_as="score"), 2)
        == 0.64
    )
    assert (
        round(calculate_edit_distance(source_cct_one_sentence, source_cct, return_as="score"), 2)
        == 0.0
    )
    assert (
        round(calculate_edit_distance(source_cct_missing_word, source_cct, return_as="score"), 2)
        == 0.57
    )
    assert (
        round(calculate_edit_distance(source_cct_addn_char, source_cct, return_as="score"), 2)
        == 0.89
    )
    assert (
        round(calculate_edit_distance(source_cct_dup_word, source_cct, return_as="score"), 2)
        == 0.79
    )


@pytest.mark.parametrize(
    ("filename", "expected_score", "expected_distance"),
    [
        ("fake-text.txt", 0.78, 38),
    ],
)
def test_calculate_edit_distance_with_filename(filename, expected_score, expected_distance):
    with open("example-docs/fake-text.txt") as f:
        source_cct = f.read()

    elements = partition(filename=f"example-docs/{filename}")
    output_cct = "\n".join([str(el) for el in elements])

    score = calculate_edit_distance(output_cct, source_cct, return_as="score")
    distance = calculate_edit_distance(output_cct, source_cct, return_as="distance")

    assert score >= 0
    assert score <= 1.0
    assert distance >= 0
    assert round(score, 2) == expected_score
    assert distance == expected_distance


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The dog loved the cat, but the cat loved the cow",
            {"the": 4, "cat": 2, "loved": 2, "dog": 1, "but": 1, "cow": 1},
        ),
        (
            "Hello my name is H a r p e r, what's your name?",
            {"hello": 1, "my": 1, "name": 2, "is": 1, "what's": 1, "your": 1},
        ),
        (
            "I have a dog and a cat, I love my dog.",
            {"i": 2, "have": 1, "a": 2, "dog": 2, "and": 1, "cat": 1, "love": 1, "my": 1},
        ),
    ],
)
def test_bag_of_words(text, expected):
    assert core.bag_of_words(text) == expected
