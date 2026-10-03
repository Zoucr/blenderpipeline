from blender_pipeline.blender.blender_linking_schema import validate_items
for items in [[],[{'kind':'materials','name':'Red','apply':'material','object_name':'Hero'},{'kind':'materials','name':'Blue','apply':'material','object_name':'Hero'}],[{'kind':'objects','name':'Hero','apply':'material'}]]:
    try:validate_items(items);raise AssertionError('invalid batch accepted')
    except ValueError:pass
assert len(validate_items([{'kind':'materials','name':'Red'},{'kind':'materials','name':'Red'}]))==1
print('PASS: duplicate selection normalization, invalid batch/type rejection and conflicting assignment guard')
