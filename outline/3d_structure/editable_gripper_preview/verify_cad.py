"""Round-trip validation for final STEP deliverables."""
from pathlib import Path
import json
import cadquery as cq
from build_models import profile, check_skin_flatness

HERE=Path(__file__).resolve().parent
results=[]
for channel in (12,32):
    for name in ('Silicone_cap.step',f'gripper-{channel}-assembled.step',f'gripper-{channel}-exploded.step'):
        path=HERE/'cad'/str(channel)/name
        shape=cq.importers.importStep(str(path)).val()
        result={'file':str(path.relative_to(HERE)),'valid':shape.isValid(),'solids':len(shape.Solids()),'volume_mm3':shape.Volume()}
        if name == 'Silicone_cap.step':
            source=cq.importers.importStep(str(HERE.parent/f'onebody-{channel}-jiegoujian.STEP')).val()
            body=max(source.Solids(),key=lambda s:s.Volume())
            result.update(check_skin_flatness(shape,profile(body)))
        results.append(result)
        print(result,flush=True)
        if not result['valid'] or result['solids']==0:
            raise ValueError(f'Invalid STEP round trip: {path}')
(HERE/'step-roundtrip-validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
