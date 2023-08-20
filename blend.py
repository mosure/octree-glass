import bpy

import math
import random


class OctreeNode:
    def __init__(self, origin, size, depth, max_depth):
        self.origin = origin
        self.size = size
        self.depth = depth
        self.max_depth = max_depth
        self.children = []

    def split(self):
        if self.depth == 0:
            return

        step = self.size / 2.0
        for dx in [-0.5, 0.5]:
            for dy in [-0.5, 0.5]:
                for dz in [-0.5, 0.5]:
                    offset = (dx * step, dy * step, dz * step)
                    child_origin = tuple(sum(i) for i in zip(self.origin, offset))
                    child = OctreeNode(child_origin, step, self.depth - 1, self.max_depth)
                    self.children.append(child)

def init_octree(node, split_prob, ior, ior_stdev, roughness):
    do_split = node.depth == node.max_depth or random.random() < split_prob

    if node.depth == 0 or not do_split:
        size = node.size
        location = node.origin

        colors = [(0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 0, 1), (1, 1, 1, 1), (1, 1, 1, 1)]
        color = random.choice(colors)

        bpy.ops.mesh.primitive_cube_add(size=size, enter_editmode=False, align='WORLD', location=location)
        cube = bpy.context.active_object
        cube.parent = bpy.data.objects["OctreeEmpty"]
        assign_material(cube, color, ior, ior_stdev, roughness)
        return

    node.split()
    for child in node.children:
        init_octree(child, split_prob, ior, ior_stdev, roughness)

def get_octree_bounds(node):
    """Recursively find the minimum and maximum bounds of the octree."""
    half_size = node.size / 2.0
    min_bound = tuple(o - half_size for o in node.origin)
    max_bound = tuple(o + half_size for o in node.origin)

    if not node.children:
        return min_bound, max_bound

    for child in node.children:
        child_min, child_max = get_octree_bounds(child)
        min_bound = tuple(min(min_bound[i], child_min[i]) for i in range(3))
        max_bound = tuple(max(max_bound[i], child_max[i]) for i in range(3))

    return min_bound, max_bound

# Assigns a glass material to an object
def assign_material(obj, color, ior, ior_stdev, roughness):
    mat = bpy.data.materials.new(name="GlassMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    shader = nodes.new(type='ShaderNodeBsdfGlass')
    shader.inputs[0].default_value = color
    shader.inputs[1].default_value = roughness
    shader.inputs[2].default_value = random.gauss(ior, ior_stdev)
    shader.location = (0,0)

    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (400,0)

    mat.node_tree.links.new(shader.outputs[0], output.inputs[0])
    obj.data.materials.append(mat)

def clear_scene():
    # Clearing cubes
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='MESH')
    bpy.ops.object.delete()

    # Clearing the OctreeEmpty and its data
    if "OctreeEmpty" in bpy.data.objects:
        bpy.data.objects["OctreeEmpty"].select_set(True)
        bpy.ops.object.delete()

    # Clearing the Octree camera and its data
    if "OctreeCam" in bpy.data.objects:
        bpy.data.objects["OctreeCam"].select_set(True)
        bpy.ops.object.delete()

    if "OctreeCam" in bpy.data.cameras:
        bpy.data.cameras.remove(bpy.data.cameras["OctreeCam"])

    # Clearing the lights and their data
    light_names = ["DichroicTopLight", "DichroicSideLight1", "DichroicSideLight2"]
    for light_name in light_names:
        if light_name in bpy.data.objects:
            bpy.data.objects[light_name].select_set(True)
            bpy.ops.object.delete()
        if light_name + "Data" in bpy.data.lights:
            bpy.data.lights.remove(bpy.data.lights[light_name + "Data"])

# Clear the octree from the scene
class OT_ClearScene(bpy.types.Operator):
    bl_idname = "scene.clear_octree"
    bl_label = "Clear Octree"

    def execute(self, context):
        clear_scene()
        return {'FINISHED'}


def rotate_empty():
    # Ensure the OctreeEmpty exists
    if "OctreeEmpty" not in bpy.data.objects:
        return

    empty = bpy.data.objects["OctreeEmpty"]

    # Set the rotation values
    rotation_x = math.radians(45)
    rotation_y = math.atan(1/math.sqrt(2))  # Roughly 35.264 degrees

    # Apply rotations
    empty.rotation_euler.x = rotation_x
    empty.rotation_euler.y = rotation_y

# Generate the octree
class OT_GenerateOctree(bpy.types.Operator):
    bl_idname = "scene.generate_octree"
    bl_label = "Generate Octree"

    def execute(self, context):
        bpy.ops.scene.clear_octree()

        if "OctreeEmpty" not in bpy.data.objects:
            bpy.ops.object.empty_add(location=(0,0,0))
            empty = bpy.context.active_object
            empty.name = "OctreeEmpty"

        depth = context.scene.octree_depth
        split_prob = context.scene.split_prob
        ior = context.scene.ior
        ior_stdev = context.scene.ior_stdev
        roughness = context.scene.roughness
        encase_thickness = context.scene.encase_thickness

        size = 2
        origin = (0, 0, 0)
        root = OctreeNode(origin, size, depth, depth)
        init_octree(root, split_prob, ior, ior_stdev, roughness)

        min_bound, max_bound = get_octree_bounds(root)
        center = tuple((min_bound[i] + max_bound[i]) / 2 for i in range(3))
        extent = max(max_bound[i] - min_bound[i] for i in range(3)) + 2 * encase_thickness

        # Create the outer box
        bpy.ops.mesh.primitive_cube_add(size=extent, enter_editmode=False, align='WORLD', location=center)
        outer_cube = bpy.context.active_object
        outer_cube.parent = bpy.data.objects["OctreeEmpty"]
        assign_material(outer_cube, (1, 1, 1, 1), ior, 0.0, roughness / 2) # outer cube doesn't get random ior

        rotate_empty()

        return {'FINISHED'}


def setup_lights(center, extent):
    light_distance = extent * 3  # distance to place the lights from the center

    # Top light
    if "DichroicTopLight" not in bpy.data.objects:
        bpy.ops.object.light_add(type='SUN', align='WORLD', location=(center[0], center[1], center[2] + light_distance))
        top_light = bpy.context.active_object
        top_light.name = "DichroicTopLight"
        top_light.data.name = "DichroicTopLightData"
        top_light.data.energy = 10
        top_light.rotation_euler = (0, 0, 0)

    # Side Light 1
    if "DichroicSideLight1" not in bpy.data.objects:
        bpy.ops.object.light_add(type='SUN', align='WORLD', location=(center[0] - light_distance, center[1], center[2]))
        side_light_1 = bpy.context.active_object
        side_light_1.name = "DichroicSideLight1"
        side_light_1.data.name = "DichroicSideLight1Data"
        side_light_1.data.energy = 10
        side_light_1.rotation_euler = (0, 3.14159 / 2, 0)

    # Side Light 2
    if "DichroicSideLight2" not in bpy.data.objects:
        bpy.ops.object.light_add(type='SUN', align='WORLD', location=(center[0], center[1] - light_distance, center[2]))
        side_light_2 = bpy.context.active_object
        side_light_2.name = "DichroicSideLight2"
        side_light_2.data.name = "DichroicSideLight2Data"
        side_light_2.data.energy = 10
        side_light_2.rotation_euler = (3.14159 / 2, 0, 0)

    return [top_light, side_light_1, side_light_2]

def setup_camera_animation(center, extent):
    # Ensure a camera exists or create a new one
    camera_distance = extent * 4  # Adjusting the distance for proper viewport fitting
    if "OctreeCam" not in bpy.data.cameras:
        bpy.ops.object.camera_add(location=(center[0], center[1] - camera_distance, center[2]))
        camera = bpy.context.active_object
        camera.name = "OctreeCam"
        camera.data.name = "OctreeCam"
    else:
        camera = bpy.data.objects["OctreeCam"]
        camera.location = (center[0], center[1] - camera_distance, center[2])  # Reset camera position

    # Create or get an Empty at the center
    if "TargetEmpty" not in bpy.data.objects:
        bpy.ops.object.empty_add(location=center)
        empty = bpy.context.active_object
        empty.name = "TargetEmpty"
    else:
        empty = bpy.data.objects["TargetEmpty"]
        empty.location = center  # Reset empty's position

    # Remove existing constraints to refresh them
    camera.constraints.clear()

    # Set track-to constraint for the camera to target the center of the octree
    track_to = camera.constraints.new(type='TRACK_TO')
    track_to.target = empty
    track_to.track_axis = 'TRACK_NEGATIVE_Z'  # Camera's direction of view
    track_to.up_axis = 'UP_Y'  # Camera's up direction

    # Keyframe the camera to rotate around the center
    frames_per_revolution = 300
    for frame in range(0, frames_per_revolution + 1, 10):
        angle = (frame / frames_per_revolution) * 2 * 3.14159
        x = center[0] + camera_distance * math.cos(angle)
        y = center[1] + camera_distance * math.sin(angle)
        camera.location = (x, y, center[2])
        camera.keyframe_insert(data_path="location", frame=frame)

    # Setup lights for desired reflections and refractions
    setup_lights(center, extent)

class OT_SetupAnimation(bpy.types.Operator):
    bl_idname = "scene.setup_animation"
    bl_label = "Setup Animation"

    def execute(self, context):
        # Get the octree bounds
        root = OctreeNode((0, 0, 0), 2, context.scene.octree_depth, context.scene.octree_depth)
        min_bound, max_bound = get_octree_bounds(root)
        center = tuple((min_bound[i] + max_bound[i]) / 2 for i in range(3))
        extent = max(max_bound[i] - min_bound[i] for i in range(3))

        # Setup camera animation
        setup_camera_animation(center, extent)
        return {'FINISHED'}


# Panel UI
class OctreePanel(bpy.types.Panel):
    bl_label = "Octree Generator v18"
    bl_idname = "VIEW3D_PT_octree"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Octree'
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "octree_depth")
        layout.prop(scene, "split_prob")
        layout.prop(scene, "roughness")
        layout.prop(scene, "ior")
        layout.prop(scene, "ior_stdev")
        layout.prop(scene, "encase_thickness")

        layout.operator("scene.setup_animation")
        layout.operator("scene.generate_octree")
        layout.operator("scene.clear_octree")

classes = [OT_ClearScene, OT_GenerateOctree, OT_SetupAnimation, OctreePanel]

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.octree_depth = bpy.props.IntProperty(name="depth", default=3, min=1, max=10)
    bpy.types.Scene.split_prob = bpy.props.FloatProperty(name="split probability", default=0.2, min=0, max=1)
    bpy.types.Scene.roughness = bpy.props.FloatProperty(name="roughness", default=0.25, min=0.1, max=2)
    bpy.types.Scene.ior = bpy.props.FloatProperty(name="IOR", default=1.45, min=1, max=3)
    bpy.types.Scene.ior_stdev = bpy.props.FloatProperty(name="IOR stdev", default=0.5, min=0, max=1)
    bpy.types.Scene.encase_thickness = bpy.props.FloatProperty(name="encase thickness", default=0.3, min=0)

def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.Scene.octree_depth
    del bpy.types.Scene.split_prob
    del bpy.types.Scene.roughness
    del bpy.types.Scene.ior
    del bpy.types.Scene.ior_stdev
    del bpy.types.Scene.encase_thickness

if __name__ == "__main__":
    register()
