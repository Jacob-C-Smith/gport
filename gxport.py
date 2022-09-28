import bpy, bmesh
import math, json, sys, time, os, getpass, importlib

from struct              import pack
from dataclasses         import dataclass
from timeit              import default_timer              as timer
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.types           import Operator, AddonPreferences
from bpy.props           import (
    StringProperty,
    BoolProperty,
    BoolVectorProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty
)

from .g10_blender import ( 
    Light,
    Camera,
    Part,
    Texture,
    Material,
    LightProbe,
    Transform,
    Rigidbody,
    Collider,
    Entity,
    Skybox,
    Scene,
    Bone,
    Pose,
    Action,
    Rig
)


def add_project_names_cb(self, context):
    items = []
    for a in bpy.context.preferences.addons['gport'].preferences.prop_collection:
        items.append((a.name, a.name, ""))
    return items

class gxport(Operator, ExportHelper):

    """
       GXPort
       TODO: light probes
    """
    bl_idname = "gport.gxport" 
    bl_label  = "Export a G10 scene"
    
    # A few constant tuples used for EnumProperties and dropdowns
    OFFSET_MODES    = (
        ('X+', "X+", "Side by Side to the Left"),
        ('Y+', "Y+", "Side by Side, Downward"),
        ('Z+', "Z+", "Stacked Above"),
        ('X-', "X-", "Side by Side to the Right"),
        ('Y-', "Y-", "Side by Side, Upward"),
        ('Z-', "Z-", "Stacked Below"),
    )
    
    CONTEXT_TABS    = {
        ("General", "General", "General"),
        ("Scene"  , "Scene"  , "Scene"),
        ("Bake"   , "Bake"   , "Bake"),
        ("Shading", "Shading", "Shading")
    }
    
    SCENE_OBJECTS   = {
        ("All"         , "All"         , "All"),
        ("Entities"    , "Entities"    , "Entities"),
        ("Cameras"     , "Cameras"     , "Cameras"),
        ("Lights"      , "Lights"      , "Lights"),
        ("Light probes", "Light probes", "Light probes" ),
        ("Empties"     , "Empties"     , "Empties" )
    }

    DEFAULT_SHADERS = {
        ("PBR"         , "Automatic PBR"   , "Auto PBR"),
        ("Forward PBR" , "Forward PBR"     , "Forward PBR"),
        ("Deferred PBR", "Deferred PBR"    , "Deferred PBR"),
        ("Diffuse"     , "Default Phong"   , "Diffuse"),
        ("Textured"    , "Default Textured", "Textured"),
        ("PBR Height"  , "PBR + Height"    , "PBR Height"),
        ("Custom"      , "Custom"          , "Custom")
    }

    IMAGE_FORMATS = {
        ("PNG", "PNG", "PNG"),
        ("JPG", "JPG", "JPG"),
        ("BMP", "BMP", "BMP"),
        ("QOI", "QOI", "QOI")
    }

    # ExportHelper mixin class uses this
    filename_ext = ""
    
    # Properties used in the exporter.
    filter_glob: StringProperty(
        default = "*.json",
        options = {'HIDDEN'},
        maxlen  = 255,  # Max internal buffer length, longer would be clamped.
    )
    
    filepath: StringProperty(
        name        = "Directory Path", 
        description = "file path", 
        maxlen      =  1024,
        default     =  "",
        subtype     = 'DIR_PATH'
    )

    relative_paths: BoolProperty(
        name        = "Relative paths",
        description = "Use relative file paths",
        default     = True,
    )

    append_selected: BoolProperty(
        name        = "Append selected",
        description = "Append selected objects to scene directory and scene file",
        default     = True,
    )
    
    # All the exporter tab properties
    context_tab: EnumProperty(
        name        = "Context tab",
        default     = "General",
        items       = CONTEXT_TABS,
        description = "Configure your scene"
    )
    
    # Scene object filter properties
    scene_objects: EnumProperty(
        name        = "Scene objects",
        default     = "All",
        items       = SCENE_OBJECTS,
        description = "Filter by objects"
    )

    # Comment
    comment: StringProperty(
        default = "Created by " + getpass.getuser(),
        name=""
    )
    
    # Properties for global orientation
    forward_axis: EnumProperty(
        name        =  "Forward",
        default     = 'Y+',
        items       = OFFSET_MODES,
        description = "Global foraward axis"
    )

    up_axis: EnumProperty(
        name        = "Up",
        default     = "Z+",
        items       = OFFSET_MODES,
        description = "Global up axis"
    )

    entity_path: StringProperty (
        default="",
        name=""
    )

    material_path: StringProperty (
        default="",
        name="",
        subtype     = 'DIR_PATH'
    )
    
    part_path: StringProperty (
        default="",
        name=""
    )
    
    texture_path: StringProperty (
        default="",
        name=""
    )

    collider_path: StringProperty (
        default="",
        name=""
    )

    audio_path: StringProperty (
        default="",
        name=""
    )

    project_names: EnumProperty(
        name = "",
        items=add_project_names_cb
    )

    # Properties for shaders
    shader_option: EnumProperty(
        name        = "",
        default     = "PBR",
        items       = DEFAULT_SHADERS,
        description = "The shader that will be used to draw entities"
    )
    
    shader_path: StringProperty(
        name    = "Path",
        default = "G10/G10 PBR.json"
    )
    
    scene_search: StringProperty(
        name    = "",
        default = ""
    )

    # Properties for PBR material export
    use_albedo: BoolProperty(
        name        = "Albedo",
        description = "The albedo map is the base color input that defines the diffuse reflectivity of the surface.",
        default     = True
    )
    
    use_normal: BoolProperty(
        name        = "Normal",
        description = "The normal map give your object texture by changing the direction light is reflected off of surfaces.",
        default     = True
    )
    
    use_rough: BoolProperty(
        name        = "Rough",
        description = "The rough map defines how light scatters across the surface.",
        default     = True
    )
    
    use_metal: BoolProperty(
        name        = "Metal",
        description = "The metal map defines where the surface is made of metal.",
        default     = True
    )
    
    use_ao: BoolProperty(
        name        = "Ambient Occlusion",
        description = "The ambient occlusion map creates softer & more realistic global shadows around the edges of objects.",
        default     = True
    )
    
    use_height: BoolProperty(
        name        = "Height",
        description = "Height maps alter the geometry of an object.",
        default     = False
    )
    
    # Vertex group properties
    use_geometric: BoolProperty(
        name        ="Geometry",
        description ="Geometric coordinates.",
        default     =True
    )

    use_uv: BoolProperty(
        name        = "Texture coordinates.",
        description = "Texture coordinates.",
        default     = True
    )

    use_normals: BoolProperty(
        name        = "Normals",
        description = "Normals",
        default     = True
    )

    use_tangents: BoolProperty(
        name        = "Tangents",
        description = "Tangents",
        default     = False
    )

    use_bitangents: BoolProperty(
        name        = "Bitangents",
        description = "Bitangents",
        default     = False
    )

    use_color: BoolProperty(
        name        = "Color",
        description = "Color",
        default     = False
    )

    use_bone_groups: BoolProperty(
        name        = "Bone groups",
        description = "Bone groups",
        default     = False
    )

    use_bone_weights: BoolProperty(
        name        = "Bone weights",
        description = "Bone weights",
        default     = False
    )
    
    # Texture export resolution property
    texture_resolution: IntProperty(
        name    = "",
        default = 2048,
        min     = 1,
        max     = 65535,
        step    = 1,
        subtype = 'PIXEL',
        description = "Texture resolution for baking"
    )

    image_format: EnumProperty(
        name        = "",
        default     = "PNG",
        items       = IMAGE_FORMATS,
        description = "The image format"
    )

    # Lighting probe properties
    light_probe_dim: IntProperty(
        name    = "",
        default = 512,
        min     = 1,
        max     = 2048,
        step    = 1,
        subtype = 'PIXEL'
    )
    
    # Execute 
    def execute(self, context):

        # Time how long it takes to export the scene
        start = timer()

        state: dict = { }

        # General state
        state['relative paths']         = self.relative_paths
        state['comment']                = self.comment

        # Global orientation
        state['forward axis']           = self.forward_axis
        state['up axis']                = self.up_axis

        # Vertex groups
        state['vertex groups']          = []
        state['vertex groups'].append("xyz"  if self.use_geometric    else None)
        state['vertex groups'].append("uv"   if self.use_uv           else None)
        state['vertex groups'].append("nxyz" if self.use_normals      else None)
        state['vertex groups'].append("txyz" if self.use_tangents     else None)
        state['vertex groups'].append("bxyz" if self.use_bitangents   else None)
        state['vertex groups'].append("rgba" if self.use_color        else None)
        state['vertex groups'].append("bg"   if self.use_bone_groups  else None)
        state['vertex groups'].append("bw"   if self.use_bone_weights else None)
        
        # Material settings
        state['material textures']      = []
        state['material textures'].append("albedo"  if self.use_albedo else None)
        state['material textures'].append("normal"  if self.use_normal else None)
        state['material textures'].append("rough"   if self.use_rough  else None)
        state['material textures'].append("metal"   if self.use_metal  else None)
        state['material textures'].append("ao"      if self.use_ao     else None)
        state['material textures'].append("height"  if self.use_height else None)

        # Shader settings
        state['shader']                 = self.shader_path

        # Bake settings
        state['texture resolution']     = self.texture_resolution
        state['image format']           = self.image_format
        state['light probe resolution'] = self.light_probe_dim

        # initialize project_path to None
        project_path = None

        # Find the correct project path from the list of project paths
        for i in bpy.context.preferences.addons['gport'].preferences.prop_collection:
            if i['name'] == self.project_names:

                # Set the project path
                project_path = i['path']

        #bpy.context.space_data.params.directory = 

        # Create a scene object
        scene = Scene(bpy.context.scene)
        
        # Write it to the directory
        scene.write_to_directory(project_path if project_path is not None else self.filepath)

        # Stop the timer
        end     = timer()
        seconds = end-start

        self.report({'INFO'}, "Export finished in %dh %dm %ds" % (int(seconds/3600),int(seconds/60), int(seconds%60)))       

        return {'FINISHED'}

    # Draw general configuration tab
    
    # Draw export config box
    def draw_export_config(self, context):
        layout = self.layout
        box    = layout.box()
        box.label(text="Project", icon="OUTLINER_COLLECTION")
        box.prop(self, "project_names")

        box = layout.box()

        # Export configuration box
        box.label(text="Export options", icon='EXPORT')
        row = box.row()
        row.active = bpy.data.is_saved
        box.prop(self, "relative_paths")
        box.prop(self, "append_selected")
        box.label(text='Comment',icon='INFO')
        box.prop(self, "comment" )
        return

    # Draw global orientation config box
    def draw_global_orientation_config(self, context):
        layout = self.layout
        box    = layout.box()
        
        # Global orientation box
        box.label(text="Global Orientation", icon='ORIENTATION_GLOBAL') 

        row = box.row()
        row.label(text="Forward Axis:", icon='AXIS_FRONT')
        row = box.row()
        row.prop(self,"forward_axis",expand=True)

        row = box.row()
        row.label(text="Up Axis:", icon='AXIS_TOP')
        row = box.row()
        row.prop(self,"up_axis",expand=True)
        
        return

    def draw_recursive_parts (self, context, box, o):
        
        # Draw Parts
        box.label(text=str(o.name))

        if bool(o.children) == True:
            b2 = box.box()

            for z in o.children:
                self.draw_recursive_parts(context, b2, z)
                
        return

    def get_mat_list (self, o, mat_list):

        for m in o.material_slots:
            if m.material is not None:
                mat_list.append(m.material.name)

        if len(o.children) > 0:
            for z in o.children:
                self.get_mat_list(z, mat_list)
                
        return

    def draw_entity(self, context, box, o):
        
        # Write the name of the entity
        row = box.row()
        row.label(text=str(o.name), icon='OBJECT_DATA')
        
        b2 = box
        
        # Draw Parts
        box.label(text=str("Parts"), icon='MESH_DATA')
        self.draw_recursive_parts(context, box.box(), o)

        # Draw materials
        mat_list = [ ]
        self.get_mat_list(o, mat_list)

        mat_list = set(mat_list)

        if len(mat_list) > 0:
            b2.label(text=str("Materials"),icon='MATERIAL')
            b3 = b2.box()

            for g in mat_list:
                b3.label(text=str(g))
                
        b2.label(text=str("Shader"),icon='SHADING_RENDERED')

        # Draw Transform
        box.label(text=str("Transform"), icon='OBJECT_ORIGIN')

        # Draw rigid body
        if o.rigid_body is not None:
            b2.label(text=str("Rigidbody"),icon='RIGID_BODY')

            # Draw collider
            if o.rigid_body.type == 'ACTIVE':
                    if o.rigid_body.collision_shape == 'CONVEX_HULL':
                        row = box.row()
                        row.label(text=str("Convex hull collider"),icon='MESH_ICOSPHERE')
                    elif o.rigid_body.collision_shape == 'BOX':
                        row = box.row()
                        row.label(text=str("Box collider"),icon='MESH_CUBE')
                    elif o.rigid_body.collision_shape == 'SPHERE':
                        row = box.row()
                        row.label(text=str("Sphere collider"),icon='MESH_UVSPHERE')
                    elif o.rigid_body.collision_shape == 'CAPSULE':
                        row = box.row()
                        row.label(text=str("Capsule collider"),icon='MESH_CAPSULE')
                    elif o.rigid_body.collision_shape == 'CYLINDER':
                        row = box.row()
                        row.label(text=str("Cylinder collider"),icon='MESH_CYLINDER')
                    elif o.rigid_body.collision_shape == 'CONE':
                        row = box.row()
                        row.label(text=str("Cone collider"),icon='MESH_CONE')

        if bool(o.parent):
            if o.parent.type == 'ARMATURE':
                box.label(text=str("Armature"), icon='ARMATURE_DATA')
                b2=box.box()
                for action in o.parent.animation_data.nla_tracks:
                    b2.label(text=str(action.name))

    def draw_objects_in_scene(self, context):        
        layout = self.layout

        box    = layout.box()
        
        box.label(text="Search", icon="VIEWZOOM")
        box.prop(self, "scene_search")
        box.label(text="Filter", icon="FILTER")
        box.prop(self, "scene_objects", expand=True)

        # Iterate over all selected objects        
        for o in bpy.context.scene.objects:
            
            if len(self.scene_search) > 0:
                if self.scene_search.lower() not in o.name.lower():
                    continue

            # Draw a camera label
            if o.type == 'CAMERA' and (self.scene_objects == 'All' or self.scene_objects == 'Cameras'):
                row = box.box()
                row.label(text=str(o.name),icon='CAMERA_DATA')
        
            # Draw a light
            elif o.type == 'LIGHT' and (self.scene_objects == 'All' or self.scene_objects == 'Lights'):
                row = box.box()
                if o.data.type == 'POINT':
                    row.label(text=str(o.name),icon='OUTLINER_DATA_LIGHT')
                elif o.data.type == 'SUN':
                    row.label(text=str(o.name),icon='LIGHT_SUN')
                elif o.data.type == 'SPOT':
                    row.label(text=str(o.name),icon='LIGHT_SPOT')
                elif o.data.type == 'AREA':
                    row.label(text=str(o.name),icon='LIGHT_AREA')

            # Draw a mesh label
            elif o.type == 'MESH' and (self.scene_objects == 'All' or self.scene_objects == 'Entities'):
                pass

            # Draw a lighting probe
            elif o.type == 'LIGHT_PROBE' and (self.scene_objects == 'All' or self.scene_objects == 'Light probes'):
                row = box.box()
                row.label(text=str(o.name),icon='OUTLINER_OB_LIGHTPROBE')

            elif o.type == 'EMPTY' and (self.scene_objects == 'All' or self.scene_objects == 'Empties'):
                row = box.box()
                print(str(o.name))
                row.label(text=str(o.name),icon='OUTLINER_OB_EMPTY')

                row.label(text=str("Transform"), icon='OBJECT_ORIGIN')

        ez = {}

        for o in bpy.context.scene.objects:
            if len(self.scene_search) > 0:
                if self.scene_search.lower() not in o.name.lower():
                    continue

            if (o.type == 'MESH') and (self.scene_objects == 'All' or self.scene_objects == 'Entities'):
                if bool(o.parent)==False:
                    ez[o.name] = o
                elif o.parent.type == 'ARMATURE' and (self.scene_objects == 'All' or self.scene_objects == 'Entities'):
                    ez[o.name] = o

        for o in ez:
            self.draw_entity(context, box.box(), ez[o])

    # Draw material and shader tab
    
    # Draw shader options
    def draw_shader_settings(self, context):
        layout = self.layout
        box    = layout.box() 

        box.label(text='Shader', icon='NODE_MATERIAL')

        box.prop(self,"shader_option")
        if   self.shader_option == 'Custom':
            box.prop(self,"shader_path")
        elif self.shader_option == 'PBR':
            self.shader_path = "G10/shaders/G10 PBR.json"
            
            self.use_albedo = True
            self.use_normal = True
            self.use_metal  = True
            self.use_rough  = True
            self.use_ao     = True
            self.use_height = False
            

            self.use_geometric    = True
            self.use_uv           = True
            self.use_normals      = True
            self.use_tangents     = False
            self.use_bitangents   = False
            self.use_color        = False
            self.use_bone_groups  = False
            self.use_bone_weights = False

        elif self.shader_option == 'Diffuse':
            self.shader_path = "G10/shaders/G10 Phong.json" 
            
            self.use_albedo = True
            self.use_normal = True
            self.use_metal  = True
            self.use_rough  = False
            self.use_ao     = False
            self.use_height = False
        elif self.shader_option == 'Textured':
            self.shader_path = "G10/shaders/G10 Textured.json"     

            self.use_albedo = True
            self.use_normal = False
            self.use_metal  = False
            self.use_rough  = False
            self.use_ao     = False
            self.use_height = False
        box.label(text=str(self.shader_path))

        global glob_shader_path
        glob_shader_path = self.shader_path
        
        return
    
    # Draw the material export options
    def draw_material_settings(self, context):
        layout = self.layout
        box = layout.box()
        
        box.label(text='Material settings', icon='MATERIAL_DATA')
        
        box.prop(self, "use_albedo")
        box.prop(self, "use_normal")
        box.prop(self, "use_rough")
        box.prop(self, "use_metal")
        box.prop(self, "use_ao")
        box.prop(self, "use_height")
        
        return
    
    # Draw the world settings
    def draw_world_settings(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text='World', icon='WORLD')

        if bpy.context.scene.world:
            if bpy.context.scene.world.name:
                box.label(text=str(bpy.context.scene.world.name))

        return

    # Draw texture resolution box
    def draw_texture_bake_settings(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='Texture', icon='TEXTURE_DATA')
        box.prop(self, "texture_resolution")
        box.prop(self, "image_format")
        return    
    
    # Draw light probe box
    def draw_light_probe_settings(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='Light  dimensions', icon='OUTLINER_OB_LIGHTPROBE')
        r=box.row()
        r.prop(self, "light_probe_dim")
        sr = r.row()
        sr.label(text=f" x {int(self.light_probe_dim * 0.75)} px")
        
        return
    
    # Draw vertex group settings
    def draw_mesh_settings(self, context):
        layout = self.layout
        box    = layout.box()
        box.label(text='Vertex groups', icon='GROUP_VERTEX')
        
        box.prop(self,"use_geometric")

        box.prop(self,"use_uv")

        box.prop(self,"use_normals")
        
        box.prop(self,"use_tangents")
    
        box.prop(self,"use_bitangents")
    
        box.prop(self,"use_color")

        box.prop(self,"use_bone_groups")

        box.prop(self,"use_bone_weights")    

        return
    
    def draw_rig_settings(self, context):
        layout = self.layout
        box    = layout.box()
        box.label(text='Rig', icon='ARMATURE_DATA')
        b2 = box.box()
        b2.label(text='')
        return
    
    def draw_collision_config(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='Collision', icon='SELECT_INTERSECT')
        for o in bpy.data.objects:
            if o in bpy.context.selected_objects:                  
                if o.type == 'MESH':
                    if o.rigid_body is not None:
                        if o.rigid_body.type == 'ACTIVE':
                            if o.rigid_body.collision_shape == 'CONVEX_HULL':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_ICOSPHERE')
                            elif o.rigid_body.collision_shape == 'BOX':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_CUBE')
                            elif o.rigid_body.collision_shape == 'SPHERE':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_UVSPHERE')
                            elif o.rigid_body.collision_shape == 'CAPSULE':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_CAPSULE')
                            elif o.rigid_body.collision_shape == 'CYLINDER':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_CYLINDER')
                            elif o.rigid_body.collision_shape == 'BOX':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_CUBE')
                            elif o.rigid_body.collision_shape == 'CONE':
                                row = box.row()
                                row.label(text=str(o.name),icon='MESH_CONE')
                        else:
                            row = box.row()
                            row.label(text=str(o.name),icon='GHOST_ENABLED')    
                    else:
                        row = box.row()
                        row.label(text=str(o.name),icon='GHOST_DISABLED')

    # Draw everything
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "context_tab",expand=True)
    
        if self.context_tab == 'Scene':
            self.draw_world_settings(context)
            self.draw_objects_in_scene(context)
        if self.context_tab == 'General':
            self.draw_export_config(context)        
            self.draw_global_orientation_config(context)
        if self.context_tab == 'Bake':
            self.draw_texture_bake_settings(context)
            self.draw_light_probe_settings(context)
        if self.context_tab == 'Shading':
            self.draw_shader_settings(context)
            self.draw_material_settings(context)
            self.draw_mesh_settings(context)

        return 