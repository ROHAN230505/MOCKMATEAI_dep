"""
Admin analytics response (Sections 7.9, 16).

Every other endpoint in this API speaks camelCase through a `CamelModel`; the
admin route was returning a service dict straight to `success()`, which meant it
alone answered in snake_case. A schema fixes that and, more usefully, pins what
this endpoint is allowed to contain — there is deliberately no field here that
could carry a user id, a name or an email.
"""
from app.schemas.common import CamelModel


class EngagementRow(CamelModel):
    module: str
    users: int
    percentage: float


class CategoryAverage(CamelModel):
    category: str
    #: None when no report has ever scored this category.
    average: float | None


class WeakestCategoryCount(CamelModel):
    category: str
    count: int
    percentage: float


class TopicAccuracy(CamelModel):
    topic: str
    answered: int
    accuracy: float | None


class TopicCompletion(CamelModel):
    topic: str
    problems: int
    solved_by_anyone: int


class NotMeasured(CamelModel):
    metric: str
    reason: str


class AdminAnalyticsOut(CamelModel):
    cohort_size: int
    #: True when the cohort is too small for an average to be an aggregate.
    suppressed: bool
    suppression_reason: str | None
    engagement: list[EngagementRow]
    category_averages: list[CategoryAverage]
    weakest_category_counts: list[WeakestCategoryCount]
    aptitude_topic_accuracy: list[TopicAccuracy]
    dsa_topic_completion: list[TopicCompletion]
    not_measured: list[NotMeasured]
