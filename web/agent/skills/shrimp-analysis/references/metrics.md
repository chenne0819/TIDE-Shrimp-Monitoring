# Metrics and data boundaries

| Field | Unit | Meaning |
| --- | --- | --- |
| length_mm | mm | Estimated length of each tracked individual |
| width_mm | mm | Width proxy converted from the detection box's short side |
| weight_g | g | Weight estimated by a regression or test model |
| shrimp_count | individuals | Sum of tracked individuals across completed videos |
| video_count | videos | Number of completed video analyses |
| sex | category | Male/Female/Unknown; never force Unknown into another category |
| water | category | clear/turbid/unknown, classified per video |

Comparability across recording conditions is unknown when complete camera-scale or model-version metadata was not saved. Length, width, weight, and water-color estimates may still come from test models. These values alone cannot support conclusions about actual farming outcomes or health.

Do not provide survival rate, stocking density, feed conversion ratio, pH, dissolved oxygen, or growth of the same shrimp across videos. The database lacks sufficient fields for these metrics.

Statistical results with `sample_unit=track` use tracking IDs within each video; `video_mean` uses each video's mean of valid measurements. Samples within a video may be correlated, and independence across videos is not guaranteed. Retain this limitation for Welch t-tests and ANOVA even when using video means. Use Pearson/Spearman results computed by the backend from actual paired measurements, never infer them from sampled scatter points. A p-value is neither an effect size nor proof of causation.
