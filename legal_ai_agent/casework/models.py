from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class WagePeriod(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: date
    end: date
    due: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    paid: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start: raise ValueError('欠薪期间结束日期早于开始日期')
        return self

class CaseFacts(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workplace: str | None = None
    employer_city: str | None = None
    dispute_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    employment_status: Literal['active','terminated','unknown'] = 'unknown'
    initiator: Literal['employer','worker','mutual','unknown'] = 'unknown'
    termination_reason: str | None = None
    termination_basis: Literal['unknown','employer_agreement','worker_38','article_40','article_41','article_39','voluntary','illegal_claim'] = 'unknown'
    article40_conditions: bool | None = None
    article40_category: Literal['unknown','medical','incompetence','objective_change'] = 'unknown'
    agreement_reached: bool | None = None
    worker38_ground: Literal['unknown','unpaid_wages','labor_conditions','unpaid_social_insurance','unlawful_rules','invalid_contract','other'] = 'unknown'
    worker38_conditions: bool | None = None
    worker38_notice_delivered: bool | None = None
    layoff_conditions: bool | None = None
    layoff_procedure: bool | None = None
    continued_performance: Literal['unknown','not_requested','requested','impossible'] = 'unknown'
    protected_status: bool | None = None
    written_notice_30: bool | None = None
    monthly_average: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    previous_month_wage: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    employment_type: Literal['ordinary','dispatch','part_time','retired','other'] = 'ordinary'
    actual_cross_border_work: bool | None = None
    cross_city_resolved: bool = False
    applicant: str | None = None
    applicant_id: str | None = None
    applicant_address: str | None = None
    applicant_phone: str | None = None
    employer_name: str | None = None
    employer_address: str | None = None
    employer_representative: str | None = None
    employer_phone: str | None = None
    wages: list[WagePeriod] = Field(default_factory=list, max_length=36)
    wage_statement: str | None = Field(default=None,max_length=2000)
    evidence: dict[str,Literal['claimed_present','missing','unknown']] = Field(default_factory=dict)

    @field_validator('workplace','employer_city', mode='before')
    @classmethod
    def normalize_city(cls,value):
        if value is None: return value
        return str(value).strip().removeprefix('广东省').removesuffix('市')

    @model_validator(mode='after')
    def dates_ordered(self):
        if self.start_date and self.end_date and self.start_date > self.end_date: raise ValueError('离职日期早于入职日期')
        periods=sorted(self.wages,key=lambda w:w.start)
        for a,b in zip(periods,periods[1:]):
            if b.start <= a.end: raise ValueError('欠薪期间重叠，须先合并或拆分核对')
        return self

def empty_case():
    return dict(schema_version=1,case_version=0,facts=CaseFacts().model_dump(mode='json'),fact_sources={},
                claims=[],sources=[],calculations=[],review_issues=[],missing_info=[],confirmation=None,
                document=None,document_status='not_generated',status='intake',revisions=[],artifacts_version=None,
                stages=[],failures=[],model_calls=[],historical_information={})
