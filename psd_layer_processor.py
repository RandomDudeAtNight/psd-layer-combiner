"""
PSD Layer Processor - Automated JPG Generation from PSD with Layer Variants
Copyright (c) 2024 - Automated version of LABODET LLC Photoshop script

This script processes PSD files to generate JPG variants by combining different layers,
mimicking the behavior of the original Photoshop script.

FIXES:
1. Fixed layer visibility not being applied correctly
2. Added proper layer state management
3. Improved color layer detection
4. Fixed layer rendering order
"""

import os
import logging
import tempfile
import traceback
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageChops
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer, Group
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

class PSDProcessor:
    """
    Main class for processing PSD files and generating JPG variants
    """
    
    def __init__(self, psd_path: str, output_dir: str = None):
        """
        Initialize the PSD processor
        
        Args:
            psd_path: Path to the PSD file
            output_dir: Directory to save output files
        """
        self.psd_path = Path(psd_path)
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp())
        self.psd = None
        self.required_groups = ['@main', 'camera', 'colors', 'base', 'bg']
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def load_psd(self) -> bool:
        """
        Load and validate PSD file structure
        
        Returns:
            bool: True if PSD loaded successfully
        """
        try:
            logger.info(f"Loading PSD file: {self.psd_path}")
            
            # Try loading with ignore_unknown_layer_properties to handle SheetColorType error
            try:
                self.psd = PSDImage.open(self.psd_path, ignore_unknown_layer_properties=True)
            except TypeError:
                # Fallback for older versions of psd-tools
                self.psd = PSDImage.open(self.psd_path)
            
            # Validate required group structure
            if not self._validate_psd_structure():
                logger.error("PSD structure validation failed")
                return False
                
            logger.info("PSD loaded and validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load PSD: {e}", exc_info=True)
            return False
    
    def _validate_psd_structure(self) -> bool:
        """
        Validate that PSD has required group structure
        
        Returns:
            bool: True if structure is valid
        """
        try:
            group_names = []
            for layer in self.psd:
                if isinstance(layer, Group):
                    group_names.append(layer.name)
            
            for required_group in self.required_groups:
                if required_group not in group_names:
                    logger.error(f"Missing required group: {required_group}")
                    return False
            
            # Check if @main contains metalware
            main_group = self._get_group_by_name('@main')
            if main_group:
                metalware_found = any('metalware' in layer.name.lower() 
                                    for layer in main_group if hasattr(layer, 'name'))
                if not metalware_found:
                    logger.warning("@main group should contain metalware layer")
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating PSD structure: {e}", exc_info=True)
            return False
    
    def _get_group_by_name(self, group_name: str) -> Optional[Group]:
        """
        Get group by name from PSD
        
        Args:
            group_name: Name of the group to find
            
        Returns:
            Group object or None if not found
        """
        for layer in self.psd:
            if isinstance(layer, Group) and layer.name == group_name:
                return layer
        return None
    
    def _get_layer_colors(self, group_name: str) -> List[str]:
        """
        Extract color names from a specific group
        
        Args:
            group_name: Name of the group to extract colors from
            
        Returns:
            List of color names
        """
        group = self._get_group_by_name(group_name)
        if not group:
            return []
        
        colors = []
        for layer in group:
            if hasattr(layer, 'name') and layer.name:
                # Extract color name (assuming format like "blue", "red", etc.)
                color_name = layer.name.lower().strip()
                if color_name and color_name not in colors:
                    colors.append(color_name)
        
        return colors
    
    def _validate_color_pairs(self) -> Dict[str, bool]:
        """
        Validate that colors exist in camera, colors, and base groups
        
        Returns:
            Dict mapping color names to validation status
        """
        camera_colors = self._get_layer_colors('camera')
        colors_group_colors = self._get_layer_colors('colors')
        base_colors = self._get_layer_colors('base')
        
        valid_colors = {}
        
        for color in camera_colors:
            # Check if color exists in both colors and base groups
            has_color = color in colors_group_colors
            has_base = color in base_colors
            valid_colors[color] = has_color and has_base
            
            if not valid_colors[color]:
                logger.warning(f"Color '{color}' missing in colors or base groups")
        
        return valid_colors
    
    def _get_all_layer_names(self, group=None, prefix=''):
        """Recursively get all layer names with their full paths"""
        if group is None:
            group = self.psd
        
        layers = []
        for layer in group:
            layer_name = f"{prefix}{layer.name}"
            layers.append(layer_name)
            if hasattr(layer, 'layers'):  # It's a group
                layers.extend(self._get_all_layer_names(layer, f"{layer_name}/"))
        return layers

    def _set_layer_visibility_fixed(self, psd, target_color):
        """
        CORRECTED: Properly set layer visibility for target color
        
        Key insight: The issue is that we're hiding the target color layers in 'base/' 
        while showing 'red' layers, causing all variants to look identical.
        """
        logger.info(f"Setting up layers for color: {target_color}")
        
        # Get all color names from all groups
        all_colors = set()
        for group_name in ['camera', 'colors', 'base']:
            group_colors = self._get_layer_colors(group_name)
            all_colors.update(group_colors)
        
        logger.info(f"Found colors: {all_colors}")
        logger.info(f"Target color: {target_color}")
        
        # Step 1: Always show these top-level groups
        for layer in psd:
            if isinstance(layer, Group):
                group_name = layer.name.lower().strip()
                if group_name in ['bg', 'base', 'colors', 'camera', '@main']:
                    layer.visible = True
                    logger.debug(f"Container group '{layer.name}' -> SHOW")
        
        # Step 2: Handle layer visibility within groups
        for layer in psd.descendants():
            if not hasattr(layer, 'visible'):
                continue
                
            layer_name = layer.name.lower().strip()
            parent_name = layer.parent.name.lower() if layer.parent else 'root'
            
            # Always show background layers
            if parent_name == 'bg':
                layer.visible = True
                logger.debug(f"Background layer '{layer.name}' -> SHOW")
                continue
            
            # Handle layers in the 'base' group - THIS IS THE KEY FIX
            if parent_name == 'base':
                # Only show the target color layer group in base
                if layer_name == target_color.lower():
                    layer.visible = True
                    logger.debug(f"Target base layer '{layer.name}' -> SHOW")
                elif layer_name in all_colors:
                    layer.visible = False
                    logger.debug(f"Non-target base layer '{layer.name}' -> HIDE")
                else:
                    layer.visible = True
                    logger.debug(f"Non-color base layer '{layer.name}' -> SHOW")
                continue
            
            # Handle layers in the 'colors' group
            if parent_name == 'colors':
                if layer_name == target_color.lower():
                    layer.visible = True
                    logger.debug(f"Target colors layer '{layer.name}' -> SHOW")
                elif layer_name in all_colors:
                    layer.visible = False
                    logger.debug(f"Non-target colors layer '{layer.name}' -> HIDE")
                else:
                    layer.visible = True
                    logger.debug(f"Non-color colors layer '{layer.name}' -> SHOW")
                continue
            
            # Handle layers in the 'camera' group
            if parent_name == 'camera':
                if layer_name == target_color.lower():
                    layer.visible = True
                    logger.debug(f"Target camera layer '{layer.name}' -> SHOW")
                elif layer_name in all_colors:
                    layer.visible = False
                    logger.debug(f"Non-target camera layer '{layer.name}' -> HIDE")
                else:
                    layer.visible = True
                    logger.debug(f"Non-color camera layer '{layer.name}' -> SHOW")
                continue
            
            # Handle layers in '@main' group
            if parent_name == '@main':
                # Show color-specific layers only if they match target
                if layer_name in all_colors:
                    if layer_name == target_color.lower():
                        layer.visible = True
                        logger.debug(f"@main layer '{layer.name}' matches target color -> SHOW")
                    else:
                        layer.visible = False
                        logger.debug(f"@main layer '{layer.name}' is non-target color -> HIDE")
                else:
                    # Non-color layers (e.g., 'steel', 'metalware') stay visible
                    layer.visible = True
                    logger.debug(f"@main non-color layer '{layer.name}' -> SHOW")
                continue
            
            # Handle layers within color groups (e.g., red/Layer 16 copy)
            if parent_name in all_colors:
                # If we're in a color group, show only if it matches our target
                if parent_name == target_color.lower():
                    layer.visible = True
                    logger.debug(f"Layer '{layer.name}' in target color group '{parent_name}' -> SHOW")
                else:
                    layer.visible = False
                    logger.debug(f"Layer '{layer.name}' in non-target color group '{parent_name}' -> HIDE")
                continue
            
            # Default: show other layers
            layer.visible = True
            logger.debug(f"Other layer '{layer.name}' (parent: {parent_name}) -> SHOW")

    def _render_layer_combination_fixed(self, color_name: str) -> Image.Image:
        """
        CORRECTED: Render layer combination with proper visibility handling and blending
        """
        # Open a fresh copy of the PSD for each render
        psd = PSDImage.open(str(self.psd_path))

        try:
            logger.info(f"Rendering combination for color: {color_name}")
            
            # Apply corrected visibility settings
            self._set_layer_visibility_fixed(psd, color_name)
            
            # Validate visibility settings
            validation_passed = self._validate_visibility_settings(psd, color_name)
            
            # Debug: Log visible layers and their blend modes
            visible_layers = []
            hidden_layers = []
            for layer in psd.descendants():
                if hasattr(layer, 'visible'):
                    parent_name = layer.parent.name if layer.parent else 'Root'
                    blend_mode = getattr(layer, 'blend_mode', 'normal')
                    opacity = getattr(layer, 'opacity', 1.0)
                    layer_info = f"{parent_name}/{layer.name} (blend: {blend_mode}, opacity: {opacity})"
                    if layer.visible:
                        visible_layers.append(layer_info)
                    else:
                        hidden_layers.append(layer_info)
            
            logger.info(f"Visible layers for {color_name}:\n" + "\n".join(f"- {l}" for l in visible_layers))
            logger.info(f"Hidden layers for {color_name}:\n" + "\n".join(f"- {l}" for l in hidden_layers))
            
            # Render the image with proper handling of blend modes and opacity
            rendered_image = None
            
            # Try composite with blend modes preserved
            try:
                logger.info("Attempting composite with blend modes...")
                rendered_image = psd.composite(layer_filter=lambda l: l.visible)
                if rendered_image and rendered_image.size[0] > 1 and rendered_image.size[1] > 1:
                    logger.info("✅ Composite with blend modes successful")
                else:   
                    logger.warning("❌ Composite with blend modes returned invalid image")
                    rendered_image = None
            except Exception as e:
                logger.error(f"❌ Composite with blend modes failed: {e}")
                rendered_image = None
            
            # Fallback: Try flattening the image to RGB to handle blend modes better
            if not rendered_image:
                try:
                    logger.info("Attempting flattened composite...")
                    # Create a new blank image with white background
                    bg_color = (255, 255, 255)  # White background
                    rendered_image = Image.new('RGB', (psd.width, psd.height), bg_color)
                    
                    # Manually composite visible layers from bottom to top
                    for layer in psd.descendants(include_clip=True):
                        if hasattr(layer, 'visible') and layer.visible:
                            try:
                                layer_img = layer.topil()
                                if layer_img:
                                    # Apply layer opacity
                                    if hasattr(layer, 'opacity') and layer.opacity < 1.0:
                                        if layer_img.mode == 'RGBA':
                                            # Create a new alpha channel with adjusted opacity
                                            alpha = layer_img.split()[3]
                                            alpha = alpha.point(lambda p: p * layer.opacity)
                                            layer_img.putalpha(alpha)
                                    
                                    # Get layer position
                                    left = layer.offset[0]
                                    top = layer.offset[1]
                                    right = left + layer_img.width
                                    bottom = top + layer_img.height
                                    
                                    # Paste the layer with alpha compositing
                                    if layer_img.mode == 'RGBA':
                                        rendered_image.paste(layer_img, (left, top, right, bottom), layer_img)
                                    else:
                                        rendered_image.paste(layer_img, (left, top, right, bottom))
                                        
                            except Exception as e:
                                logger.warning(f"Failed to process layer {layer.name}: {e}")
                    
                    if rendered_image and rendered_image.size[0] > 1 and rendered_image.size[1] > 1:
                        logger.info("✅ Flattened composite successful")
                    else:
                        logger.warning("❌ Flattened composite returned invalid image")
                        rendered_image = None
                        
                except Exception as e:
                    logger.error(f"❌ Flattened composite failed: {e}")
                    rendered_image = None
            
            # Final fallback: Create debug image
            if not rendered_image:
                logger.error("All rendering methods failed, creating debug image")
                from PIL import ImageDraw, ImageFont
                debug_img = Image.new('RGB', (800, 600), color=(255, 0, 0))
                draw = ImageDraw.Draw(debug_img)
                try:
                    font = ImageFont.truetype("arial.ttf", 24)
                except:
                    font = ImageFont.load_default()
                
                draw.text((10, 10), f"Render failed for: {color_name}", fill="white", font=font)
                draw.text((10, 50), f"Validation: {'PASSED' if validation_passed else 'FAILED'}", fill="white", font=font)
                
                return debug_img
            
            # Convert to RGB and return
            if rendered_image.mode != 'RGB':
                rendered_image = rendered_image.convert('RGB')
            
            # Final verification: Check if image has actual content
            bbox = rendered_image.getbbox()
            if bbox:
                logger.info(f"✅ Rendered image has content (bbox: {bbox})")
            else:
                logger.warning("❌ Rendered image appears to be empty")
            
            return rendered_image
                
        except Exception as e:
            logger.error(f"Error in render_layer_combination_fixed: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Clean up
            if hasattr(psd, 'close'):
                psd.close()

    def _validate_visibility_settings(self, psd, target_color):
        """
        Enhanced validation to ensure visibility is set correctly
        """
        all_colors = set()
        for group_name in ['camera', 'colors', 'base']:
            group_colors = self._get_layer_colors(group_name)
            all_colors.update(group_colors)
        
        target_color_layers_visible = 0
        other_color_layers_visible = 0
        
        for layer in psd.descendants():
            if not hasattr(layer, 'visible') or not hasattr(layer, 'name'):
                continue
                
            layer_name = layer.name.lower().strip()
            parent_name = layer.parent.name.lower() if layer.parent else 'root'
            
            # Check direct color layers (in colors, camera, base groups)
            if parent_name in ['colors', 'camera', 'base'] and layer_name in all_colors:
                if layer.visible:
                    if layer_name == target_color.lower():
                        target_color_layers_visible += 1
                    else:
                        other_color_layers_visible += 1
            
            # Check layers within color groups
            elif parent_name in all_colors:
                if layer.visible:
                    if parent_name == target_color.lower():
                        target_color_layers_visible += 1
                    else:
                        other_color_layers_visible += 1
        
        logger.info(f"Visibility validation: {target_color_layers_visible} target layers visible, {other_color_layers_visible} other color layers visible")
        
        # For proper isolation, we should have target color layers visible but no other color layers
        if target_color_layers_visible > 0 and other_color_layers_visible == 0:
            logger.info("✅ Visibility validation PASSED")
            return True
        else:
            logger.warning("❌ Visibility validation FAILED")
            return False

    def _render_layer_combination(self, color_name: str) -> Image.Image:
        """
        Use the fixed rendering method
        """
        return self._render_layer_combination_fixed(color_name)

    def _should_show_layer(self, layer, layers_to_show: List[str]) -> bool:
        """
        Determine if a layer should be visible based on naming rules
        
        Args:
            layer: PSD layer object
            layers_to_show: List of layer names that should be visible
            
        Returns:
            bool: True if layer should be shown
        """
        if not hasattr(layer, 'name') or not layer.name:
            return False
        
        layer_name = layer.name.lower().strip()
        parent_name = layer.parent.name.lower() if hasattr(layer, 'parent') and layer.parent else ''
        
        # Always show @main group layers
        if parent_name == '@main':
            return True
        
        # Show bg group layers
        if parent_name == 'bg':
            return True
        
        # For color variants, check if this layer matches any of our target colors
        for target in layers_to_show:
            target = target.lower()
            # Check if target is in layer name or parent group name
            if (target in layer_name or 
                (hasattr(layer, 'parent') and layer.parent and 
                 target in getattr(layer.parent, 'name', '').lower())):
                return True
        
        return False
    
    def _render_layer(self, layer) -> Optional[Image.Image]:
        """
        Render a single layer to PIL Image
        
        Args:
            layer: PSD layer object
            
        Returns:
            PIL Image or None if layer cannot be rendered
        """
        try:
            if isinstance(layer, PixelLayer):
                # Get layer image
                layer_image = layer.topil()
                if layer_image:
                    # Position the layer correctly
                    positioned_image = Image.new('RGBA', 
                                               (self.psd.width, self.psd.height), 
                                               (0, 0, 0, 0))
                    positioned_image.paste(layer_image, (layer.left, layer.top))
                    return positioned_image
            
            elif isinstance(layer, Group):
                # Render group as composite
                group_image = Image.new('RGBA', 
                                      (self.psd.width, self.psd.height), 
                                      (0, 0, 0, 0))
                
                for sublayer in reversed(list(layer)):
                    sublayer_image = self._render_layer(sublayer)
                    if sublayer_image:
                        group_image = Image.alpha_composite(group_image, sublayer_image)
                
                return group_image if group_image else None
                
        except Exception as e:
            logger.warning(f"Failed to render layer {layer.name}: {e}")
            return None
    
    def generate_variants(self) -> List[Dict]:
        """
        Generate all JPG variants based on color combinations
        
        Returns:
            List of dictionaries containing variant information
        """
        if not self.psd:
            logger.error("PSD not loaded")
            return []
        
        # Get valid color combinations
        valid_colors = self._validate_color_pairs()
        valid_color_names = [color for color, is_valid in valid_colors.items() if is_valid]
        
        if not valid_color_names:
            logger.error("No valid color combinations found")
            return []
        
        # Extract base filename from PSD
        base_filename = self.psd_path.stem
        
        variants = []
        
        logger.info(f"Generating variants for {len(valid_color_names)} colors: {valid_color_names}")
        
        for color in valid_color_names:
            try:
                logger.info(f"Processing color variant: {color}")
                
                # Render the combination
                variant_image = self._render_layer_combination(color)
                
                # Verify the image is valid and different
                if variant_image.size[0] <= 1 or variant_image.size[1] <= 1:
                    logger.error(f"Invalid image size for color {color}: {variant_image.size}")
                    continue
                
                # Calculate image hash before saving
                import hashlib
                image_hash = hashlib.md5(variant_image.tobytes()).hexdigest()
                
                # Save the variant
                output_filename = f"{base_filename}-{color}-metalware_1.jpg"
                output_path = self.output_dir / output_filename
                variant_image.save(output_path, quality=95, subsampling=0)
                
                # Calculate file hash after saving
                with open(output_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                
                # Get file size for verification
                file_size = output_path.stat().st_size
                
                variants.append({
                    'filename': output_filename,
                    'path': str(output_path),
                    'color': color,
                    'metalware': 'metalware',
                    'size': variant_image.size,
                    'file_size': file_size,
                    'image_hash': image_hash,
                    'file_hash': file_hash
                })
                
                logger.info(f"Generated variant: {output_filename}")
                logger.info(f"  Size: {variant_image.size}, File size: {file_size} bytes")
                logger.info(f"  Image hash: {image_hash}")
                logger.info(f"  File hash: {file_hash}")
                
                # Force garbage collection to free up resources
                import gc
                gc.collect()
                
            except Exception as e:
                logger.error(f"Failed to generate variant for color {color}: {e}")
                logger.error(traceback.format_exc())
                continue
        
        # Check for duplicate hashes
        self._check_duplicate_variants(variants)
        
        logger.info(f"Successfully generated {len(variants)} variants")
        return variants
    
    def _check_duplicate_variants(self, variants: List[Dict]):
        """Check for duplicate variants and log warnings"""
        hash_groups = {}
        
        for variant in variants:
            file_hash = variant['file_hash']
            if file_hash not in hash_groups:
                hash_groups[file_hash] = []
            hash_groups[file_hash].append(variant['color'])
        
        for file_hash, colors in hash_groups.items():
            if len(colors) > 1:
                logger.warning(f"⚠️  DUPLICATE DETECTED: Colors {colors} have identical file hash {file_hash}")
            else:
                logger.info(f"✅ Unique variant: {colors[0]} (hash: {file_hash})")
        
        # Additional check: Compare image content
        if len(variants) > 1:
            from PIL import ImageChops
            base_variant = variants[0]
            base_image = Image.open(base_variant['path'])
            
            for variant in variants[1:]:
                try:
                    compare_image = Image.open(variant['path'])
                    diff = ImageChops.difference(base_image, compare_image)
                    if diff.getbbox():
                        logger.info(f"✅ Images {base_variant['color']} and {variant['color']} are visually different")
                    else:
                        logger.warning(f"⚠️  Images {base_variant['color']} and {variant['color']} are visually identical")
                except Exception as e:
                    logger.error(f"Error comparing images: {e}")
    
    def process(self) -> Tuple[bool, List[Dict]]:
        """
        Main processing function
        
        Returns:
            Tuple of (success, variants_list)
        """
        try:
            # Load PSD
            if not self.load_psd():
                return False, []
            
            # Generate variants
            variants = self.generate_variants()
            
            if not variants:
                logger.error("No variants generated")
                return False, []
            
            logger.info(f"Processing completed successfully. Generated {len(variants)} variants")
            return True, variants
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            logger.error(traceback.format_exc())
            return False, []
    
    def cleanup(self):
        """Clean up temporary files"""
        try:
            if self.psd:
                self.psd.close()
        except:
            pass


def main():
    """
    Main function for testing
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python psd_processor.py <psd_file> [output_dir]")
        sys.exit(1)
    
    psd_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    processor = PSDProcessor(psd_file, output_dir)
    success, variants = processor.process()
    
    if success:
        print(f"Successfully processed {len(variants)} variants:")
        for variant in variants:
            print(f"  - {variant['filename']} ({variant['file_size']} bytes)")
    else:
        print("Processing failed")
        sys.exit(1)
    
    processor.cleanup()


if __name__ == "__main__":
    main()