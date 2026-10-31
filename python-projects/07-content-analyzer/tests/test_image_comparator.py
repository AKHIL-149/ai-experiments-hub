"""Comparing two images: exact identity, pixel similarity, AI rating and the combined score."""
import random

import pytest
from PIL import Image, ImageDraw

from src.core.image_comparator import ImageComparator


def scene(seed: int, size=(400, 300)) -> Image.Image:
    """A made-up picture with structure (blocks of different brightness), reproducible per seed."""
    rnd = random.Random(seed)
    image = Image.new('RGB', size, (rnd.randrange(256),) * 3)
    draw = ImageDraw.Draw(image)
    for _ in range(25):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        draw.rectangle([x, y, x + rnd.randrange(20, 150), y + rnd.randrange(20, 150)],
                       fill=tuple(rnd.randrange(256) for _ in range(3)))
    return image


class FakeVision:
    backend = 'ollama'

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def analyze(self, prompt, images, temperature=0.7, max_tokens=1000):
        self.calls.append({'prompt': prompt, 'images': len(images), 'temperature': temperature, 'max_tokens': max_tokens})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


cmp_ = ImageComparator()


# ------------------------------------------------------------------ structural

def test_identical_images():
    a = scene(1)
    result = cmp_.compare_images(a, a.copy())
    assert result['identical'] and result['similarity_score'] == 100
    assert result['structural']['visual_similarity'] == 100


def test_unrelated_images_of_the_same_size_do_not_score_as_similar():
    # matching dimensions used to be worth 20 points on their own
    result = cmp_.compare_images(scene(1), scene(2))
    assert result['similar_dimensions'] is True
    assert result['similarity_score'] <= 10 and not result['identical']


def test_a_resized_copy_is_recognised_as_the_same_picture():
    a = scene(3)
    result = cmp_.compare_images(a, a.resize((200, 150)))
    assert result['similar_dimensions'] is False
    assert result['similarity_score'] >= 90


def test_a_recompressed_copy_is_recognised():
    import io
    a = scene(4)
    buffer = io.BytesIO()
    a.save(buffer, 'JPEG', quality=40)
    b = Image.open(io.BytesIO(buffer.getvalue()))
    assert cmp_.compare_images(a, b)['similarity_score'] >= 90


def test_a_slightly_edited_copy_scores_between_the_extremes():
    a = scene(5)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([0, 0, 200, 150], fill=(255, 255, 255))
    score = cmp_.compare_images(a, b)['similarity_score']
    assert 20 < score < 100


def test_same_pixels_in_different_colour_modes_or_formats_are_identical():
    a = scene(6)
    assert cmp_.compare_images(a, a.convert('RGBA'))['identical']
    assert cmp_.compare_images(a, a.convert('RGB'))['identical']


def test_one_changed_pixel_is_not_identical():
    a = scene(7)
    b = a.copy()
    b.putpixel((10, 10), (1, 2, 3))
    assert not cmp_.compare_images(a, b)['identical']


def test_same_pixels_with_different_dimensions_are_not_identical():
    a = Image.new('RGB', (4, 2), 'red')
    b = Image.new('RGB', (2, 4), 'red')                     # same bytes, different shape
    assert not cmp_.compare_images(a, b)['identical']


def test_structural_report_fields():
    a, b = scene(1, (400, 300)), scene(2, (200, 150))
    s = cmp_.compare_images(a, b)['structural']
    assert s['image1']['dimensions'] == '400x300' and s['image2']['dimensions'] == '200x150'
    assert s['same_aspect_ratio'] is True and s['same_dimensions'] is False
    assert s['dimension_diff'] == {'width_diff': 200, 'height_diff': 150, 'width_ratio': 2.0, 'height_ratio': 2.0}


def test_hash_of_a_big_image_is_computed_in_bands_and_matches_a_whole_image_hash():
    import hashlib
    tall = scene(8, (50, 700))
    whole = hashlib.sha256(b'50x700' + tall.tobytes()).hexdigest()
    assert cmp_._calculate_image_hash(tall) == whole


# ------------------------------------------------------------------ the combined score

def structural(identical=False, visual=0):
    return {'identical': identical, 'visual_similarity': visual}


@pytest.mark.parametrize('ai,visual,expected', [
    (100, 0, 100),        # the AI says "same scene": that is the score (it used to cap at 76)
    (85, 0, 85),
    (0, 0, 0),            # an AI rating of 0 is a real answer
    (30, 95, 95),         # near-duplicates are never rated "different"
    (None, 40, 40),       # no rating: pixel similarity
])
def test_score_rules_with_an_ai_rating(ai, visual, expected):
    comparison = {'extracted_similarity': ai} if ai is not None else {'extracted_similarity': None}
    assert cmp_._calculate_similarity_score(structural(visual=visual), comparison) == expected


def test_score_without_ai_and_for_identical():
    assert cmp_._calculate_similarity_score(structural(visual=33), None) == 33
    assert cmp_._calculate_similarity_score(structural(identical=True), {'extracted_similarity': 5}) == 100


# ------------------------------------------------------------------ AI comparison

def test_ollama_describes_each_image_alone_then_compares_the_texts():
    vision = FakeVision(['Subject: beach', 'Subject: beach', 'Same scene.\nSimilarity rating: 90%'])
    result = ImageComparator(vision).compare_images(scene(1), scene(2), temperature=0.5, max_tokens=700)
    ai = result['ai_analysis']
    assert ai['strategy'] == 'describe_then_compare' and ai['descriptions'] == ['Subject: beach'] * 2
    assert [c['images'] for c in vision.calls] == [1, 1, 0]
    assert [c['temperature'] for c in vision.calls[:2]] == [0.0, 0.0]        # descriptions must be repeatable
    assert [c['max_tokens'] for c in vision.calls[:2]] == [200, 200]
    assert vision.calls[2]['max_tokens'] == 700 and vision.calls[2]['temperature'] == 0.5
    assert 'Image 1: Subject: beach' in vision.calls[2]['prompt']
    assert ai['extracted_similarity'] == 90 and result['similarity_score'] == 90


def test_other_providers_get_both_images_in_one_call():
    vision = FakeVision(['They differ. Similarity rating: 20%'])
    vision.backend = 'anthropic'
    ai = ImageComparator(vision).compare_images(scene(1), scene(2))['ai_analysis']
    assert ai['strategy'] == 'joint' and vision.calls[0]['images'] == 2


def test_ai_failure_is_reported_and_the_score_falls_back_to_pixels():
    vision = FakeVision([RuntimeError('model down')])
    vision.backend = 'anthropic'
    result = ImageComparator(vision).compare_images(scene(1), scene(1).resize((200, 150)))
    assert result['ai_analysis']['error'] == 'model down'
    assert result['similarity_score'] >= 90


@pytest.mark.parametrize('mode', ['content', 'visual', 'detailed', 'something-else'])
def test_modes_pick_a_prompt(mode):
    vision = FakeVision(['x'])
    vision.backend = 'openai'
    ImageComparator(vision).compare_images(scene(1), scene(2), mode=mode)
    assert vision.calls[0]['prompt']


@pytest.mark.parametrize('text,expected', [
    ('Similarity rating: 80-100%', 90),
    ('Similarity rating: 75%', 75),
    ('Rate: similarity score 62%', 62),
    ('They are 40% alike', 40),
    ('similarity: 55', 55),
    ('Similarity rating: 150%', None),
    ('no numbers here', None),
    ('The left one is 30% darker.\nSimilarity rating: 85%', 85),
])
def test_similarity_is_read_from_the_reply(text, expected):
    assert cmp_._extract_similarity_score(text) == expected


def test_find_duplicates_groups_exact_copies():
    a, b = scene(1), scene(2)
    groups = cmp_.find_duplicates([a, b, a.copy(), scene(3), b.copy(), a.copy()])
    assert sorted(groups) == [[0, 2, 5], [1, 4]]
    assert cmp_.find_duplicates([]) == []
