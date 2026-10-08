"""Optional research prosody features; importing this module needs no ML packages."""
from __future__ import annotations

import math

# Preselected before evaluation. Do not include absolute F0 or microphone level.
# These still reflect speaker/language/task differences and require transfer tests.
PROSODY_DESCRIPTORS = (
    "F0semitoneFrom27.5Hz_sma3nz_stddevNorm",
    "F0semitoneFrom27.5Hz_sma3nz_pctlrange0-2",
    "F0semitoneFrom27.5Hz_sma3nz_meanRisingSlope",
    "F0semitoneFrom27.5Hz_sma3nz_stddevRisingSlope",
    "F0semitoneFrom27.5Hz_sma3nz_meanFallingSlope",
    "F0semitoneFrom27.5Hz_sma3nz_stddevFallingSlope",
    "loudness_sma3_stddevNorm", "loudness_sma3_pctlrange0-2",
    "jitterLocal_sma3nz_amean", "jitterLocal_sma3nz_stddevNorm",
    "shimmerLocaldB_sma3nz_amean", "shimmerLocaldB_sma3nz_stddevNorm",
    "HNRdBACF_sma3nz_amean", "HNRdBACF_sma3nz_stddevNorm",
    "loudnessPeaksPerSec", "VoicedSegmentsPerSec",
    "MeanVoicedSegmentLengthSec", "StddevVoicedSegmentLengthSec",
    "MeanUnvoicedSegmentLength", "StddevUnvoicedSegmentLength",
)
PROSODY_FEATURES = tuple("prosody_" + name for name in PROSODY_DESCRIPTORS)


class ProsodyExtractor:
    """Bundled eGeMAPSv02, CPU only, no network or transcript calls."""

    def __init__(self):
        import opensmile
        self.smile = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                                     feature_level=opensmile.FeatureLevel.Functionals,
                                     num_workers=1)
        if not set(PROSODY_DESCRIPTORS) <= set(self.smile.feature_names):
            raise ValueError("Installed eGeMAPS does not expose expected descriptors")

    def extract(self, samples, sample_rate=16000):
        result = self.smile.process_signal(samples, sample_rate)
        if len(result) != 1:
            raise ValueError("Expected one eGeMAPS row per audio window")
        values = {}
        for raw_name, name in zip(PROSODY_DESCRIPTORS, PROSODY_FEATURES):
            value = float(result.iloc[0][raw_name])
            values[name] = value if math.isfinite(value) else None
        return values
