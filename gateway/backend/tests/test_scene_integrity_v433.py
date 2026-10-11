"""Scene QA tests: catch frozen and persistent dual-portrait divider patterns."""
import pytest
from PIL import Image,ImageDraw
import scene_integrity_v433 as scene

def two_still_portrait_pan_frames():
    frames=[]
    for n in range(3):
        im=Image.new("RGB",(384,384),(18,22,35))
        d=ImageDraw.Draw(im)
        # Two external portrait panels stay divided even if limbs move.
        d.rectangle((15,25,185,355),fill=(75+18*n,108,147))
        d.rectangle((207,25,370,355),fill=(87,111+11*n,82))
        d.rectangle((187,0,206,384),fill=(15,17,24))
        d.line((187,0,187,384),fill=(240,237,230),width=2)
        d.line((207,0,207,384),fill=(240,237,230),width=2)
        d.ellipse((57+n*5,90,126+n*5,173),fill=(208,153,112))
        d.ellipse((262+n*4,85,337+n*4,169),fill=(210,156,117))
        frames.append(im)
    return frames

def shared_stage_frames():
    frames=[]
    for n in range(3):
        im=Image.new("RGB",(384,384),(30+n*7,36+n*4,70+n*5))
        d=ImageDraw.Draw(im)
        d.rectangle((0,255,384,384),fill=(40+n*3,48,64))
        for x in range(10,384,17):
            d.ellipse((x,315+n%3,x+8,330+n%3),fill=(175+n*4,110,90))
        for x,col in [(100,(60,100,220)),(265,(230,105,65))]:
            d.ellipse((x-32,100+n*4,x+32,168+n*4),fill=(210,148,104))
            d.rectangle((x-45,175+n*4,x+45,264+n*4),fill=col)
            d.line((x-45,215+n*4,x-63,170+n*6),fill=(200,152,115),width=12)
        frames.append(im)
    return frames

def test_user_reported_failure_type_is_detected():
    result=scene.analyze_frames(two_still_portrait_pan_frames(),duration=8.04)
    assert result.output_is_split_layout,result
    assert not result.scene_context_verified
    assert not result.stage_verified
    assert not result.singing_language_verified
    assert len(result.persistent_dividers)>=2

def test_real_shared_stage_not_rejected_merely_for_two_characters():
    result=scene.analyze_frames(shared_stage_frames(),duration=8)
    assert not result.output_is_split_layout,result
    assert not result.stage_verified
    assert not result.two_distinct_actor_identities_verified

def test_near_static_not_automatically_successful():
    im=shared_stage_frames()[0]
    out=scene.analyze_frames([im.copy(),im.copy(),im.copy()],duration=8)
    assert out.near_static_frames

def test_no_unqualified_semantic_claim():
    out=scene.analyze_frames(shared_stage_frames(),duration=3.0)
    assert all(not getattr(out,field) for field in (
        "scene_context_verified","stage_verified","crowd_size_verified",
        "singing_language_verified","lip_sync_verified",
        "two_distinct_actor_identities_verified"))

@pytest.mark.parametrize("duration",[-1,0,17])
def test_scene_invalid_duration(duration):
    with pytest.raises(scene.SceneAnalysisError):
        scene.analyze_frames(shared_stage_frames(),duration=duration)
