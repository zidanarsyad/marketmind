"""The MarketMind agent team."""
from .analyst_chat import AnalystChatAgent
from .competitor_analyst import CompetitiveIntelligenceAgent
from .consumer_insight import ConsumerInsightAgent
from .critic import QualityAssuranceAgent
from .data_collector import DataCollectionAgent
from .data_quality import DataQualityAgent
from .director import ResearchDirectorAgent
from .forecaster import DemandForecastingAgent
from .market_analyst import MarketTrendAnalystAgent
from .reporter import ReportWriterAgent
from .segmentation import SegmentationAgent
from .strategist import StrategyAgent

PIPELINE_AGENTS = [
    ResearchDirectorAgent, DataCollectionAgent, DataQualityAgent, MarketTrendAnalystAgent, CompetitiveIntelligenceAgent,
    ConsumerInsightAgent, SegmentationAgent, DemandForecastingAgent, StrategyAgent, ReportWriterAgent,
    QualityAssuranceAgent,
]

__all__ = [a.__name__ for a in PIPELINE_AGENTS] + ["AnalystChatAgent", "PIPELINE_AGENTS"]
