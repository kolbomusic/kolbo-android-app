"""AdMob rewarded credits: signatures, receipt anti-replay contract and basic economics."""
import base64,pytest,time
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec
import rewarded_credits as credits

NOW=1791648000000  # test-only fixed UTC timestamp

def sign_query(priv,message):
    signature=priv.sign(message.encode('utf-8'),ec.ECDSA(hashes.SHA256()))
    sig=base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
    return message+'&signature='+sig+'&key_id=123456789'

@pytest.fixture
def signing():
    priv=ec.generate_private_key(ec.SECP256R1())
    pub=priv.public_key().public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv,{123456789:pub}

@pytest.fixture
def signed(signing):
    priv,keys=signing
    params=[
        'ad_network=5450213213286189855',
        'ad_unit=correct_ad_unit_abc',
        'custom_data='+'Z'*32,
        'reward_amount=2',
        'reward_item=kolbo_video_points',
        'timestamp='+str(NOW),
        'transaction_id='+'a'*40,
        'user_id='+'f'*64,
    ]
    return sign_query(priv,'&'.join(params)),keys

def verify(raw,keys):
    return credits.verify_admob_reward(raw,keys,
        expected_ad_unit='correct_ad_unit_abc',
        expected_reward_item='kolbo_video_points',
        expected_reward_amount=2,now_ms=NOW)

def test_valid_signed_google_style_callback(signed):
    raw,keys=signed
    evidence=verify(raw,keys)
    assert evidence.transaction_id=='a'*40
    assert evidence.intent_nonce=='Z'*32
    assert evidence.owner_fingerprint=='f'*64
    assert evidence.points==2

@pytest.mark.parametrize('needle,replacement',[
    ('reward_amount=2','reward_amount=5000'),
    ('ad_unit=correct_ad_unit_abc','ad_unit=wrong_ad_unit'),
    ('transaction_id='+'a'*40,'transaction_id='+'b'*40),
    ('user_id='+'f'*64,'user_id='+'0'*64),
    ('timestamp='+str(NOW),'timestamp='+str(NOW-90*3600*1000)),
])
def test_signed_data_tampering_rejected(signed,needle,replacement):
    raw,keys=signed
    with pytest.raises(credits.UnverifiedReward):
        verify(raw.replace(needle,replacement),keys)

def test_wrong_google_key_and_malformed_callback_rejected(signed,signing):
    raw,keys=signed
    priv,_=signing
    other=ec.generate_private_key(ec.SECP256R1())
    other_pem=other.public_key().public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with pytest.raises(credits.UnverifiedReward):
        verify(raw,{123456789:other_pem})
    with pytest.raises(credits.UnverifiedReward):
        verify(raw.replace('&signature=','&extra=abc&signature='),keys)
    with pytest.raises(credits.UnverifiedReward):
        verify(raw.replace('key_id=123456789','key_id=123456788'),keys)
    with pytest.raises(credits.UnverifiedReward):
        verify(raw.replace('&signature=','&key_id=123456789&signature='),keys)

def test_no_owner_intent_fails_even_with_valid_signature(signing):
    priv,keys=signing
    raw=sign_query(priv,'&'.join([
        'ad_unit=correct_ad_unit_abc','reward_amount=2','reward_item=kolbo_video_points',
        'timestamp='+str(NOW),'transaction_id='+'a'*40,'user_id='+'f'*64]))
    with pytest.raises(credits.UnverifiedReward):
        verify(raw,keys)

def test_economics_do_not_claim_one_ad_pays_for_video():
    assert credits.funding_estimate_impressions(.2,10)==20
    assert credits.funding_estimate_impressions(.2,5)==40
    assert credits.funding_estimate_impressions(0,10)==0
    with pytest.raises(ValueError):
        credits.funding_estimate_impressions(.2,0)

def test_ledger_schema_has_immutable_unique_transactions_and_owner_bound_intents():
    sql=credits.reward_schema_sql()
    assert 'transaction_id text PRIMARY KEY' in sql
    assert 'nonce text UNIQUE NOT NULL' in sql
    assert 'owner_fingerprint text NOT NULL' in sql
    assert 'state text NOT NULL' in sql
