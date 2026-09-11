"""Import the gripper into an existing Blender scene without clearing it."""
from pathlib import Path
import argparse
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_api import load_mesh, ASSET_ROOT


def set_explode(root, value):
    import bpy
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('explode must be between 0 and 1')
    root['explode'] = value
    root.update_tag()
    bpy.context.view_layer.update()


def import_model(channel=32, explode=.8, asset_root=None, collection=None):
    """Return a parent Empty. Child objects retain stable English part IDs.

    Coordinates are scaled from CAD mm into the current scene's physical unit.
    Moving/rotating/scaling the returned parent moves the complete module.
    root['explode'] drives each part's translation; the source mesh stays intact.
    No scene settings, existing objects, or existing collections are removed.
    """
    import bpy
    data = load_mesh(channel, asset_root=asset_root)
    scene = bpy.context.scene
    meters_per_unit = scene.unit_settings.scale_length if scene.unit_settings.system != 'NONE' else 1.0
    factor = .001/meters_per_unit
    target = bpy.data.collections.new(f'Gripper_{channel}')
    (collection or scene.collection).children.link(target)
    root = bpy.data.objects.new(f'Gripper_{channel}', None)
    target.objects.link(root)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 5*factor
    root['revision'] = data['revision']
    root['channel'] = int(channel)
    root['source_coordinates'] = 'original STEP XYZ; mm'
    root['millimeters_to_blender_units'] = factor
    root['explode'] = 0.0
    root.id_properties_ui('explode').update(min=0.0,max=1.0,soft_min=0.0,soft_max=1.0,
                                          description='0 = assembled; 1 = fully exploded')
    for part in data['parts']:
        mesh = bpy.data.meshes.new(part['id'])
        mesh.from_pydata([tuple(v*factor for v in p) for p in part['vertices']],[],part['triangles'])
        if mesh.validate():
            raise ValueError(f"Invalid source tessellation: {part['id']}")
        mesh.update()
        for face in mesh.polygons:
            face.use_smooth = True
        obj = bpy.data.objects.new(part['id'],mesh)
        target.objects.link(obj)
        obj.parent = root
        obj['part_id'] = part['id']
        obj['label_zh'] = part['name']
        obj['category'] = part['category']
        obj['step_component_name'] = part['step_component_name']
        obj['step_relative_path'] = part['step_file'] or ''
        obj['explode_translation_cad_mm'] = part['explode_translation_cad_mm']
        rgb = [int(part['color_srgb'][i:i+2],16)/255 for i in (1,3,5)]
        rgba = tuple(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb)+(1.0,)
        material = bpy.data.materials.new(f"{part['id']}_material")
        material.diffuse_color = rgba
        material.use_nodes = True
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = rgba
        shader.inputs['Roughness'].default_value = .37 if part['category']=='silicone' else .57
        shader.inputs['Metallic'].default_value = .3 if part['category']=='sensors' else .04
        mesh.materials.append(material)
        obj.color = rgba
        for axis,value in enumerate(part['explode_translation_cad_mm']):
            driver = obj.driver_add('location',axis).driver
            variable = driver.variables.new()
            variable.name = 'explosion'
            variable.type = 'SINGLE_PROP'
            variable.targets[0].id = root
            variable.targets[0].data_path = '["explode"]'
            driver.expression = f'explosion*{value*factor:.16g}'
    set_explode(root,explode)
    return root


def export_glb(root, filename):
    """Export just this model in its current state, preserving other selections."""
    import bpy
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    try:
        for obj in selected:
            obj.select_set(False)
        for obj in [root,*root.children]:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = root
        filename = Path(filename).resolve()
        filename.parent.mkdir(parents=True,exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=str(filename),export_format='GLB',
                                  use_selection=True,export_animations=False,export_extras=True)
    finally:
        for obj in list(bpy.context.selected_objects):
            obj.select_set(False)
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active


def main():
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel',type=int,choices=(12,32),default=32)
    parser.add_argument('--explode',type=float,default=.8)
    parser.add_argument('--asset-root',type=Path,default=ASSET_ROOT)
    parser.add_argument('--save',type=Path)
    parser.add_argument('--glb',type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    root = import_model(args.channel,args.explode,args.asset_root)
    if args.glb:
        export_glb(root,args.glb)
    if args.save:
        args.save.resolve().parent.mkdir(parents=True,exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.save.resolve()))
    print(f'Imported Gripper_{args.channel}: {len(root.children)} separate objects',flush=True)


if __name__ == '__main__':
    main()
