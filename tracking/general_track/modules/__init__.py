from .obb_track import extract_obb_track_id, track_obb_frame

__all__ = ["HeadTailShrimpAnalyzer", "ShrimpSexRatioAnalyzer", "extract_obb_track_id", "track_obb_frame"]


def __getattr__(name):
    if name in {"HeadTailShrimpAnalyzer", "ShrimpSexRatioAnalyzer"}:
        from .head_tail_pipeline import HeadTailShrimpAnalyzer
        return HeadTailShrimpAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
