"""Run only in a fresh background Blender process; build and verify final assets."""
from pathlib import Path
import hashlib
import json
import sys
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from import_blender import import_model, set_explode, export_glb
from model_api import ASSET_ROOT, load_mesh, load_manifest


def bounds(objects):
    points = [obj.matrix_world @ Vector(p) for obj in objects for p in obj.bound_box]
    return [min(p[i] for p in points) for i in range(3)]+[max(p[i] for p in points) for i in range(3)]


def verify_root(root, channel):
    source = load_mesh(channel)
    objects = {o['part_id']:o for o in root.children}
    assert len(objects)==len(source['parts'])
    factor = root['millimeters_to_blender_units']
    max_error = 0.0
    for part in source['parts']:
        obj = objects[part['id']]
        assert len(obj.data.vertices)==len(part['vertices'])
        assert len(obj.data.polygons)==len(part['triangles'])
        assert obj.data.materials
        for actual,expected in zip(obj.data.vertices,part['vertices']):
            max_error=max(max_error,*(abs(actual.co[i]/factor-expected[i]) for i in range(3)))
    assert max_error<1e-4,max_error
    max_explode_error = 0.0
    for e in (0.0,.8,1.0):
        set_explode(root,e)
        for part in source['parts']:
            obj = objects[part['id']]
            error=max(abs(obj.location[i]/factor-part['explode_translation_cad_mm'][i]*e) for i in range(3))
            max_explode_error=max(max_explode_error,error)
            assert error<1e-4,error
    return {'component_count':len(objects),'max_vertex_error_mm':max_error,
            'max_explode_error_mm':max_explode_error,
            'explode_values_checked':[0,.8,1]}


def configure_view(root):
    scene=bpy.context.scene
    box=bounds(list(root.children))
    center=Vector([(box[i]+box[i+3])/2 for i in range(3)])
    radius=max(box[i+3]-box[i] for i in range(3))
    camera_data=bpy.data.cameras.new('PreviewCamera')
    camera=bpy.data.objects.new('PreviewCamera',camera_data)
    scene.collection.objects.link(camera)
    back=Vector((-.69,-.2,.7)).normalized()
    right=Vector((0,1,0)).cross(back).normalized()
    up=back.cross(right).normalized()
    orientation=Matrix((right,up,back)).transposed().to_quaternion()
    camera.location=center+back*radius*3
    camera.rotation_euler=orientation.to_euler()
    camera_data.type='ORTHO'
    camera_data.clip_start=.0001
    points=[orientation.inverted() @ (obj.matrix_world @ Vector(p)-center)
            for obj in root.children for p in obj.bound_box]
    left,right_edge=min(p.x for p in points),max(p.x for p in points)
    bottom,top=min(p.y for p in points),max(p.y for p in points)
    shift=orientation @ Vector(((left+right_edge)/2,(bottom+top)/2,0))
    camera.location+=shift
    center+=shift
    camera_data.ortho_scale=max(right_edge-left,(top-bottom)*1200/900)*1.15
    camera_data.lens=50
    scene.camera=camera
    scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='STUDIO'
    scene.display.shading.color_type='MATERIAL'
    scene.display.shading.background_type='VIEWPORT'
    scene.display.shading.background_color=(.9,.91,.9)
    if scene.world is None:
        scene.world=bpy.data.worlds.new('PreviewWorld')
    scene.world.color=(.8,.8,.8)
    scene.render.resolution_x=1200
    scene.render.resolution_y=900
    scene.render.resolution_percentage=100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_distance=radius*1.7
                area.spaces.active.region_3d.view_location=center
                area.spaces.active.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
                area.spaces.active.clip_start=.0001
                area.spaces.active.shading.color_type='MATERIAL'
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    root.select_set(True)
    bpy.context.view_layer.objects.active=root


def main():
    if not bpy.app.background:
        raise RuntimeError('Build in a fresh background Blender process; this command resets the scene')
    output=ASSET_ROOT/'blender'
    output.mkdir(exist_ok=True)
    results=[]
    for channel in (12,32):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.preferences.filepaths.save_version=0
        bpy.context.scene.unit_settings.system='METRIC'
        bpy.context.scene.unit_settings.scale_length=1.0
        bpy.context.scene.unit_settings.length_unit='MILLIMETERS'
        # Import must leave pre-existing scene objects and transforms intact.
        sentinel=bpy.data.objects.new('Existing_model',None)
        bpy.context.scene.collection.objects.link(sentinel)
        sentinel.location=(1,2,3)
        root=import_model(channel)
        assert tuple(sentinel.location)==(1,2,3) and sentinel.name in bpy.data.objects
        bpy.data.objects.remove(sentinel,do_unlink=True)
        result=verify_root(root,channel)
        set_explode(root,0)
        assembled_bounds=bounds(list(root.children))
        export_glb(root,output/f'gripper-{channel}.glb')
        set_explode(root,.8)
        configure_view(root)
        bpy.ops.wm.save_as_mainfile(filepath=str(output/f'gripper-{channel}.blend'), compress=False)
        # Re-open the saved native file and verify persisted driver behavior.
        bpy.ops.wm.open_mainfile(filepath=str(output/f'gripper-{channel}.blend'))
        root=bpy.data.objects[f'Gripper_{channel}']
        verify_root(root,channel)
        set_explode(root,.8)
        bpy.context.scene.render.filepath=str(output/f'gripper-{channel}.png')
        bpy.ops.render.render(write_still=True)
        # Re-import GLB into an empty scene and compare physical bounds and IDs.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(output/f'gripper-{channel}.glb'))
        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
        assert len(meshes)==result['component_count']
        assert {o.get('part_id') for o in meshes}=={p['id'] for p in load_manifest()['models'][str(channel)]['parts']}
        error=max(abs(a-b) for a,b in zip(bounds(meshes),assembled_bounds))
        assert error<1e-7,error
        result.update({'channel':channel,'blend_roundtrip':True,'glb_roundtrip':True,
                       'glb_bounds_error_m':error,'existing_scene_preserved':True})
        results.append(result)
        print(json.dumps(result),flush=True)
    # Unit conversion in a millimeter-scaled existing scene is a separate case.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=.001
    root=import_model(12,0)
    verify_root(root,12)
    report={'blender_version':bpy.app.version_string,
            'mesh_sha256':hashlib.sha256((ASSET_ROOT/'mesh-data.json').read_bytes()).hexdigest(),
            'millimeter_scene_checked':True,'models':results,
            'solidworks_live_tested':False}
    (ASSET_ROOT/'interface/blender-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Blender assets and validation complete.',flush=True)


if __name__=='__main__':
    main()
