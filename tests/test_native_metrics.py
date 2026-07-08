"""Hand-computed fixtures for boundary F1 / PQ / STP (Tier C scorers)."""
from tbdoc.scoring.native import boundary_f1, panoptic_quality, segmentation_metrics


def test_perfect_segmentation():
    m = segmentation_metrics([3, 6], [3, 6], 9)
    assert m["primary"] == 1.0 and m["boundary_f1"] == 1.0 and m["perfect"] == 1.0


def test_no_boundaries_predicted():
    # gold: [0-2][3-5], pred: [0-5]. One gold doc unmatched.
    # pred doc IoU with each gold doc = 3/6 = 0.5, NOT > 0.5 -> no matches.
    m = panoptic_quality([], [3], 6)
    assert m["pq"] == 0.0
    f = boundary_f1([], [3], 6)
    assert f["recall"] == 0.0 and f["precision"] == 1.0  # no false positives


def test_every_page_a_boundary_degenerate():
    # the degenerate baseline the literature warns about: pred singletons everywhere.
    # gold [0-3][4-7]; pred 8 singletons: IoU 1/4 each -> no match -> PQ 0.
    m = panoptic_quality(list(range(1, 8)), [4], 8)
    assert m["pq"] == 0.0
    # but on singleton-heavy gold it scores high -> why PQ is primary, not F1
    g = boundary_f1(list(range(1, 8)), list(range(1, 8)), 8)
    assert g["f1"] == 1.0


def test_partial_match_hand_computed():
    # gold: [0,1][2,3,4][5]; pred: [0,1][2,3][4,5]
    # matches: {0,1} IoU 1.0; {2,3} vs {2,3,4} IoU 2/3 > .5; {4,5} vs {5} IoU .5 NOT >.5
    # tp=2 fp=1 fn=1 -> RQ = 4/(4+1+1) = 2/3; SQ = (1 + 2/3)/2 = 5/6; PQ = 5/9
    m = panoptic_quality([2, 4], [2, 5], 6)
    assert abs(m["rq"] - 2 / 3) < 1e-3
    assert abs(m["sq"] - 5 / 6) < 1e-3
    assert abs(m["pq"] - 5 / 9) < 1e-3


def test_boundary_f1_hand_computed():
    # gold boundaries {2,5}, pred {2,4}: tp=1, prec=1/2, rec=1/2, f1=1/2
    f = boundary_f1([2, 4], [2, 5], 8)
    assert f["precision"] == 0.5 and f["recall"] == 0.5 and f["f1"] == 0.5
