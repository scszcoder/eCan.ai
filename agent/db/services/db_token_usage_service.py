"""
Token Usage Database Service

Provides database operations for token usage tracking and aggregation.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import func, extract, and_
from sqlalchemy.orm import Session

from .base_service import BaseService
from ..models.token_usage_model import TokenUsage
from utils.logger_helper import logger_helper as logger


class DBTokenUsageService(BaseService):
    """
    Database service for token usage operations.
    
    Handles CRUD operations and aggregation queries for token usage data.
    """
    
    def __init__(self, engine=None, session: Session = None):
        """Initialize token usage service."""
        super().__init__(engine, session)
    
    @classmethod
    def initialize(cls, db_manager) -> 'DBTokenUsageService':
        """
        Initialize token usage service with database manager.
        
        Args:
            db_manager: ECDBMgr instance
            
        Returns:
            DBTokenUsageService: Initialized service instance
        """
        if db_manager is None:
            raise ValueError("db_manager cannot be None")
        
        engine = db_manager.get_engine()
        service = cls(engine=engine)
        service.db_manager = db_manager
        return service
    
    def record_usage(
        self,
        source_type: str,
        vendor: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        source_id: Optional[str] = None,
        source_name: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        node_type: Optional[str] = None,
        operation: Optional[str] = None,
        usage_timestamp: Optional[datetime] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        skill_name: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Record a token usage entry.
        
        Args:
            source_type: Source type (skill_llm_node, mcp_rag, etc.)
            vendor: LLM vendor (openai, anthropic, etc.)
            model: Model name (gpt-4, claude-3-opus, etc.)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_usd: Cost in USD
            source_id: Optional source identifier
            source_name: Optional human-readable source name
            user_email: Optional user email
            session_id: Optional session ID
            node_type: Optional node type
            operation: Optional operation type
            usage_timestamp: Optional timestamp (defaults to now)
            
        Returns:
            TokenUsage: Created token usage record or None on error
        """
        try:
            with self.session_scope() as session:
                usage = TokenUsage(
                    source_type=source_type,
                    source_id=source_id,
                    source_name=source_name,
                    user_email=user_email,
                    session_id=session_id,
                    vendor=vendor,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    cost_usd=cost_usd,
                    usage_timestamp=usage_timestamp or datetime.utcnow(),
                    node_type=node_type,
                    operation=operation,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    skill_name=skill_name
                )
                
                session.add(usage)
                session.flush()
                
                logger.debug(f"[TokenUsageService] Recorded usage: {source_type} - {model} - {input_tokens + output_tokens} tokens (${cost_usd:.4f})")
                return usage
                
        except Exception as e:
            logger.error(f"[TokenUsageService] Error recording usage: {e}")
            return None
    
    def get_usage_rows(
        self,
        start_utc: datetime,
        end_utc: datetime,
        user_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Raw usage rows in the half-open UTC window [start_utc, end_utc).

        Returns lightweight dicts (detached from the session) so the caller can
        bucket by local time and apportion cost. Used by the billing drill-down
        (daily → hourly → per-model); the window is always bounded to at most a
        month, so the row count stays modest.
        """
        try:
            with self.session_scope() as session:
                q = session.query(
                    TokenUsage.usage_timestamp,
                    TokenUsage.vendor,
                    TokenUsage.model,
                    TokenUsage.input_tokens,
                    TokenUsage.output_tokens,
                    TokenUsage.total_tokens,
                    TokenUsage.cost_usd,
                ).filter(
                    and_(
                        TokenUsage.usage_timestamp >= start_utc,
                        TokenUsage.usage_timestamp < end_utc,
                    )
                )
                if user_email:
                    q = q.filter(TokenUsage.user_email == user_email)
                rows = []
                for r in q.all():
                    rows.append({
                        'usage_timestamp': r.usage_timestamp,
                        'vendor': r.vendor or '',
                        'model': r.model or '',
                        'input_tokens': int(r.input_tokens or 0),
                        'output_tokens': int(r.output_tokens or 0),
                        'total_tokens': int(r.total_tokens or 0),
                        'cost_usd': float(r.cost_usd or 0.0),
                    })
                return rows
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting usage rows: {e}")
            return []

    def get_monthly_usage(
        self,
        year: int,
        month: int,
        user_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated token usage for a specific month.
        
        Args:
            year: Year
            month: Month (1-12)
            user_email: Optional user email filter
            
        Returns:
            Dict with aggregated usage data
        """
        try:
            with self.session_scope() as session:
                # Build query
                query = session.query(
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd')
                ).filter(
                    and_(
                        extract('year', TokenUsage.usage_timestamp) == year,
                        extract('month', TokenUsage.usage_timestamp) == month
                    )
                )
                
                # Add user filter if provided
                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)
                
                result = query.first()
                
                return {
                    'input_tokens': int(result.input_tokens or 0),
                    'output_tokens': int(result.output_tokens or 0),
                    'total_tokens': int(result.total_tokens or 0),
                    'cost_usd': float(result.cost_usd or 0.0),
                    'month': month,
                    'year': year
                }
                
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting monthly usage: {e}")
            return {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'cost_usd': 0.0,
                'month': month,
                'year': year
            }
    
    def get_usage_by_source(
        self,
        start_date: datetime,
        end_date: datetime,
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get token usage grouped by source type.
        
        Args:
            start_date: Start date
            end_date: End date
            user_email: Optional user email filter
            
        Returns:
            List of dicts with usage by source
        """
        try:
            with self.session_scope() as session:
                query = session.query(
                    TokenUsage.source_type,
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd'),
                    func.count(TokenUsage.id).label('count')
                ).filter(
                    and_(
                        TokenUsage.usage_timestamp >= start_date,
                        TokenUsage.usage_timestamp <= end_date
                    )
                ).group_by(TokenUsage.source_type)
                
                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)
                
                results = query.all()
                
                return [
                    {
                        'source_type': r.source_type,
                        'input_tokens': int(r.input_tokens or 0),
                        'output_tokens': int(r.output_tokens or 0),
                        'total_tokens': int(r.total_tokens or 0),
                        'cost_usd': float(r.cost_usd or 0.0),
                        'count': int(r.count or 0)
                    }
                    for r in results
                ]
                
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting usage by source: {e}")
            return []
    
    def get_usage_by_model(
        self,
        start_date: datetime,
        end_date: datetime,
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get token usage grouped by model.
        
        Args:
            start_date: Start date
            end_date: End date
            user_email: Optional user email filter
            
        Returns:
            List of dicts with usage by model
        """
        try:
            with self.session_scope() as session:
                query = session.query(
                    TokenUsage.vendor,
                    TokenUsage.model,
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd'),
                    func.count(TokenUsage.id).label('count')
                ).filter(
                    and_(
                        TokenUsage.usage_timestamp >= start_date,
                        TokenUsage.usage_timestamp <= end_date
                    )
                ).group_by(TokenUsage.vendor, TokenUsage.model)
                
                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)
                
                results = query.all()
                
                return [
                    {
                        'vendor': r.vendor,
                        'model': r.model,
                        'input_tokens': int(r.input_tokens or 0),
                        'output_tokens': int(r.output_tokens or 0),
                        'total_tokens': int(r.total_tokens or 0),
                        'cost_usd': float(r.cost_usd or 0.0),
                        'count': int(r.count or 0)
                    }
                    for r in results
                ]
                
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting usage by model: {e}")
            return []
    
    def get_recent_usage(
        self,
        limit: int = 100,
        user_email: Optional[str] = None
    ) -> List[TokenUsage]:
        """
        Get recent token usage records.
        
        Args:
            limit: Maximum number of records to return
            user_email: Optional user email filter
            
        Returns:
            List of TokenUsage records
        """
        try:
            with self.session_scope() as session:
                query = session.query(TokenUsage).order_by(
                    TokenUsage.usage_timestamp.desc()
                ).limit(limit)
                
                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)
                
                return query.all()
                
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting recent usage: {e}")
            return []

    def get_time_series_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = 'hour',  # 'hour', 'day', 'month'
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get token usage aggregated by time buckets.

        Returns list of dicts: [{period, input_tokens, output_tokens, total_tokens, cost_usd, invocation_count}]
        """
        try:
            with self.session_scope() as session:
                if granularity == 'hour':
                    # Group by date + hour
                    period_expr = func.strftime('%Y-%m-%d %H:00', TokenUsage.usage_timestamp)
                elif granularity == 'day':
                    period_expr = func.strftime('%Y-%m-%d', TokenUsage.usage_timestamp)
                else:  # month
                    period_expr = func.strftime('%Y-%m', TokenUsage.usage_timestamp)

                query = session.query(
                    period_expr.label('period'),
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd'),
                    func.count(TokenUsage.id).label('invocation_count')
                ).filter(
                    and_(
                        TokenUsage.usage_timestamp >= start_date,
                        TokenUsage.usage_timestamp < end_date
                    )
                ).group_by('period').order_by('period')

                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)

                results = query.all()

                return [
                    {
                        'period': r.period,
                        'input_tokens': int(r.input_tokens or 0),
                        'output_tokens': int(r.output_tokens or 0),
                        'total_tokens': int(r.total_tokens or 0),
                        'cost_usd': float(r.cost_usd or 0.0),
                        'invocation_count': int(r.invocation_count or 0)
                    }
                    for r in results
                ]
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting time series usage: {e}")
            return []

    def get_breakdown_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        user_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get per-model and per-skill token breakdown for a specific period.
        Also returns total invocation count.

        Returns: {
            'by_model': [{'vendor': str, 'model': str, 'total_tokens': int, 'cost_usd': float, 'count': int}],
            'by_skill': [{'skill_name': str, 'total_tokens': int, 'cost_usd': float, 'count': int}],
            'total_invocations': int
        }
        """
        try:
            with self.session_scope() as session:
                base_filter = and_(
                    TokenUsage.usage_timestamp >= start_date,
                    TokenUsage.usage_timestamp < end_date
                )

                # Per-model breakdown
                model_query = session.query(
                    TokenUsage.vendor,
                    TokenUsage.model,
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd'),
                    func.count(TokenUsage.id).label('count')
                ).filter(base_filter).group_by(TokenUsage.vendor, TokenUsage.model)

                if user_email:
                    model_query = model_query.filter(TokenUsage.user_email == user_email)

                model_results = model_query.all()

                # Per-skill breakdown
                skill_query = session.query(
                    TokenUsage.skill_name,
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd'),
                    func.count(TokenUsage.id).label('count')
                ).filter(base_filter).group_by(TokenUsage.skill_name)

                if user_email:
                    skill_query = skill_query.filter(TokenUsage.user_email == user_email)

                skill_results = skill_query.all()

                # Total invocation count
                count_query = session.query(
                    func.count(TokenUsage.id)
                ).filter(base_filter)

                if user_email:
                    count_query = count_query.filter(TokenUsage.user_email == user_email)

                total_invocations = count_query.scalar() or 0

                return {
                    'by_model': [
                        {
                            'vendor': r.vendor,
                            'model': r.model,
                            'input_tokens': int(r.input_tokens or 0),
                            'output_tokens': int(r.output_tokens or 0),
                            'total_tokens': int(r.total_tokens or 0),
                            'cost_usd': float(r.cost_usd or 0.0),
                            'count': int(r.count or 0)
                        }
                        for r in model_results
                    ],
                    'by_skill': [
                        {
                            'skill_name': r.skill_name or 'unknown',
                            'input_tokens': int(r.input_tokens or 0),
                            'output_tokens': int(r.output_tokens or 0),
                            'total_tokens': int(r.total_tokens or 0),
                            'cost_usd': float(r.cost_usd or 0.0),
                            'count': int(r.count or 0)
                        }
                        for r in skill_results
                    ],
                    'total_invocations': int(total_invocations)
                }
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting breakdown: {e}")
            return {'by_model': [], 'by_skill': [], 'total_invocations': 0}

    def get_daily_usage(self, user_email: Optional[str] = None) -> Dict[str, Any]:
        """Get today's total token usage for alarm display."""
        try:
            with self.session_scope() as session:
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow_start = today_start + timedelta(days=1)

                query = session.query(
                    func.sum(TokenUsage.input_tokens).label('input_tokens'),
                    func.sum(TokenUsage.output_tokens).label('output_tokens'),
                    func.sum(TokenUsage.total_tokens).label('total_tokens'),
                    func.sum(TokenUsage.cost_usd).label('cost_usd')
                ).filter(
                    and_(
                        TokenUsage.usage_timestamp >= today_start,
                        TokenUsage.usage_timestamp < tomorrow_start
                    )
                )

                if user_email:
                    query = query.filter(TokenUsage.user_email == user_email)

                result = query.first()

                return {
                    'input_tokens': int(result.input_tokens or 0),
                    'output_tokens': int(result.output_tokens or 0),
                    'total_tokens': int(result.total_tokens or 0),
                    'cost_usd': float(result.cost_usd or 0.0)
                }
        except Exception as e:
            logger.error(f"[TokenUsageService] Error getting daily usage: {e}")
            return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_usd': 0.0}
