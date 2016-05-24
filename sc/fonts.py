import json
import regex
import hashlib
from tempfile import NamedTemporaryFile
from fontTools.ttLib import TTFont
from fontTools import subset

import sc
import sc.textdata

import logging

logger = logging.getLogger(__name__)

def sanitize_font_name(name):
    return name.rstrip('_-.0123456789')

fonts_dir = sc.static_dir / 'fonts'
fonts_json_file = fonts_dir / 'fonts.json'
fonts_output_dir = fonts_dir / 'compiled'

font_header = '''
/* This file is generated automatically by sc/fonts.py
 *
 * DO NOT EDIT THIS FILE MANUALLY
 *
 * If a new font file is added, edit ''' + str(fonts_json_file.relative_to(sc.base_dir)) + '''
 * This will cause the required @font-face declarations to be generated.
*/
'''

font_face_template = '''
@font-face {{
    font-family: '{family}';
    font-weight: {weight};
    font-style: {style};
    src: url('{url}.woff2') format('woff2') /* {size[woff2]} */,
         url('{url}.woff') format('woff');
}}
'''


def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def name_to_var(name):
    out = name.replace(' ', '-')
    out = regex.sub(r'(\p{lower})(\p{Upper})', r'\1-\2', out)
    return out.lower()

def get_fonts_data():
    try:
        with fonts_json_file.open() as f:
            return json.load(f)
    except json.decoder.JSONDecodeError:
        logging.error('Error while processing %s', str(fonts_json_file))
        raise
    

def compile_fonts(flavors=['woff', 'woff2']):
    import json
    import hashlib
    from fontTools.ttLib import TTFont
    import fontTools.subset
    
    tim = sc.textdata.tim()
    
    font_face_decls = []
    
    if not fonts_output_dir.exists():
        fonts_output_dir.mkdir()
    
    font_data = get_fonts_data()
    fonts_seen = set()
    font_keys = set()
    
    def get_font_details(font_name):
        font_name = font_name.lower()
        result = {}
        result.update(font_data['defaults'])
        for key, value in sorted(font_data["families"].items(), key=lambda t: len(t[0]), reverse=True):
            if font_name.startswith(key.lower()):
                fonts_seen.add(key)
                result["key"] = key
                leftovers = font_name[len(key): ]
                
                if not value:
                    return None
                if isinstance(value, str):
                    result["family"] = value
                    font_keys.add((key, value))
                elif isinstance(value, list):
                    result["subset"] = value
                elif isinstance(value, dict):
                    result["subset"] = [value]
                elif not value:
                    pass
                break
        else:
            logger.error('Font file %s does not have a matching entry in fonts.json', font_name)
            return None
        
        for key, weight in sorted(font_data["weights"].items(), key=lambda t: len(t[0]), reverse=True):
            if key in leftovers:
                result["weight"] = weight
                break
        else:
            result["weight"] = "normal"
        
        for key, style in sorted(font_data["styles"].items(), key=lambda t: len(t[0]), reverse=True):
            if key in leftovers:
                result["style"] = style
                break
        else:
            result["style"] = "normal"
        return result
    
    seen = {}
    
    compiled_fonts = set(fonts_output_dir.glob('**/*'))
    valid_compiled_fonts = set()
    
    for file in sorted(fonts_dir.glob('**/*')):
        changed = False
        nonfree = "nonfree" in file.parts
        if file in compiled_fonts:
            continue
        if file.suffix not in {'.ttf', '.otf', '.woff', '.woff2'}:
            continue
        
        base_name = sanitize_font_name(file.stem)
        if base_name in seen:
            logger.error('Font file %s is too similiar to other file %s, skipping', file, seen[base_name])
        seen[base_name] = file
        
        with file.open('rb') as f:
            font_binary_data = f.read()
        md5 = hashlib.md5(font_binary_data)
        
        font_details = get_font_details(file.stem)
        
        if not font_details:
            continue
        
        if font_details['subset']:
            if font_details['weight'] in {'bold', 'semibold'}:
                weight = 'bold'
            elif font_details['style'] in {'italic'}:
                weight = 'italic'
            else:
                weight = 'normal'
            for subset_details in font_details['subset']:
                subset_languages = subset_details['subset_languages']
                subset_unicodes = set()
                
                if subset_languages == '*':
                    subset_unicodes.update(tim.get_codepoints_used(lang_uid=None, weight_or_style=weight))
                
                else:
                    if isinstance(subset_languages, str):
                        subset_languages = [subset_languages]
                    
                    for language in subset_languages:
                        codepoints = tim.get_codepoints_used(lang_uid=language, weight_or_style=weight)
                        if codepoints is None:
                            logger.error('Error in fonts.json, language uid "{}" not found in TIM'.format(language))
                        else:
                            subset_unicodes.update(codepoints)
                subset_text = ''.join(subset_unicodes)
                subset_text = ''.join(sorted(subset_text.lower() + subset_text.upper()))
                subset_md5 = md5.copy()
                subset_md5.update(subset_text.encode(encoding='utf8'))
                
                if nonfree and not sc.config.app['debug']:
                    outname = ''
                else:
                    outname = name_to_var(subset_details['name']) + '_'
                
                
                outname += weight.replace('normal', 'regular')
                if subset_languages != '*':
                    outname += '_' + '_'.join(subset_languages)
                outname += '_' + subset_md5.hexdigest()[:12]
                base_outfile = fonts_output_dir / outname
                
                suffix = font_details['save_as'][0]
                
                primary_out_file = base_outfile.with_suffix('.' + suffix)
                valid_compiled_fonts.add(primary_out_file)
                if not primary_out_file.exists():
                    changed = True
                    with NamedTemporaryFile('w+t') as subset_text_file:
                        subset_text_file.write(subset_text)
                        subset_text_file.flush()
                        fontTools.subset.main(args=[str(file), 
                                        #'--layout-features=*',
                                        #'--glyph-names',
                                        #'--symbol-cmap',
                                        #'--legacy-cmap',
                                        #'--notdef-glyph',
                                        #'--notdef-outline',
                                        #'--recommended-glyphs',
                                        #'--name-IDs=*',
                                        #'--name-legacy',
                                        #'--name-languages=*',
                                        '--output-file={}'.format(str(primary_out_file)),
                                        '--text-file={}'.format(subset_text_file.name), 
                                        '--flavor={}'.format(suffix),
                                        '--desubroutinize'])
                font = None
                size = {}
                for flavor in font_details['save_as'][1:]:
                    suffix = '.{}'.format(flavor)
                    outfile = base_outfile.with_suffix(suffix)
                    valid_compiled_fonts.add(outfile)
                    if not outfile.exists():
                        changed = True
                        if font is None:
                            font = TTFont(str(primary_out_file))
                        font.flavor = flavor
                        font.save(file=str(outfile))
                    size[flavor] = sizeof_fmt(outfile.stat().st_size)

                font_face_decls.append(font_face_template.format(url='/fonts/compiled/{}'.format(outname), 
                                                                 family=subset_details['name'], 
                                                                 weight=font_details['weight'], 
                                                                 style=font_details['style'],
                                                                 size=size,
                                                                 ))
        else:
            size = {}
            md5sum = md5.hexdigest()[:12]
            outname = md5sum if (nonfree and not sc.config.app['debug']) else "{}_{}".format(base_name, md5sum)
            base_outfile = fonts_output_dir / outname
            
            font = None
            for flavor in flavors:
                suffix = '.{}'.format(flavor)
                outfile = base_outfile.with_suffix(suffix)
                valid_compiled_fonts.add(outfile)
                if not outfile.exists():
                    changed = True
                    if outfile.suffix == file.suffix:
                        with outfile.open('wb') as f:
                            f.write(font_binary_data)
                    else:
                        if font is None:
                            font = TTFont(str(file))
                        font.flavor = flavor
                        font.save(file=str(outfile))
                size[flavor] = sizeof_fmt(outfile.stat().st_size)
        
            if font_details:
                font_face_decls.append(font_face_template.format(url='/fonts/compiled/{}'.format(outname), size=size, **font_details))
        if changed:
            print('Processed {!s}'.format(file.name))
    unneeded_fonts = compiled_fonts - valid_compiled_fonts
    if unneeded_fonts:
        print('Removing {} unused compiled fonts'.format(len(unneeded_fonts)))
        for file in unneeded_fonts:
            file.unlink()
    
    def details_to_variable(details):
        if isinstance(details, list):
            raise TypeError('details should not be a list')
        if isinstance(details, str):
            name = details
            variable = name_to_var(name)
        else:
            if 'var' in details:
                variable = details['var']
                name = details['name']
            else:
              name = details['name']
              variable = name_to_var(name)
        return {"variable": variable, "name": name}
    
    variable_decls = []
    for key, details in sorted(font_data["families"].items()):
        if details:
          variable_decls.extend(details_to_variable(details) for details in (details if isinstance(details, list) else [details]))

    with (sc.static_dir / 'css' / 'fonts' / 'fonts-auto.scss').open('w') as f:
        f.write(font_header)

        f.writelines("${variable}: '{name}';\n".format(**e) for e in variable_decls)
        f.writelines(font_face_decls)
    
    for key in set(font_data["families"]) - fonts_seen:
        logger.error('Font family mapping matches no font file: {} ({})'.format(key, font_data["families"][key]))
