from src.services.normalizer import normalize_company_name, normalize_lead
from src.sources.base import LeadRecord


def test_company_name_normalization_removes_common_suffix():
    assert normalize_company_name("  ACME Trading, LTD. ") == "acme trading"


def test_landline_is_normalized_to_e164():
    lead = normalize_lead(
        LeadRecord(
            company_name="Example Company",
            phone="(202) 456-1111",
            country="US",
            source_url="https://example.com",
            source_type="test",
        )
    )
    assert lead.normalized_phone == "+12024561111"
    assert lead.verification_status == "verified"
    assert lead.is_business_phone is True


def test_mobile_number_is_not_classified_as_business_phone():
    lead = normalize_lead(
        LeadRecord(
            company_name="Example",
            phone="+44 7400 123456",
            country="GB",
            source_url="https://example.com",
            source_type="test",
        )
    )
    assert lead.is_business_phone is False
    assert lead.verification_status == "mobile"
