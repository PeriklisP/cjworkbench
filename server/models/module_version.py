# ModuleVersion is a module that keeps track of the different versions of a
# single module, thereby allowing users to create workflows with different
# versions of the same module. This could be for a myriad of reasons, including
# backward compatibiity (not everyone's ready to use the latest version of a
# module), beta testing, etc.
#
# [adamhooper, 2018-12-27] ... and we support zero of those reasons.

import os
import json
import jsonschema
import yaml
from django.contrib.postgres.fields import JSONField
from django.db import models, transaction
from django.core.exceptions import ValidationError
from .Module import Module


_SpecPath = os.path.join(os.path.dirname(__file__), 'module_spec_schema.yaml')
with open(_SpecPath, 'rt') as spec_file:
    _SpecSchema = yaml.load(spec_file)
_validator = jsonschema.Draft7Validator(
    _SpecSchema,
    format_checker=jsonschema.FormatChecker()
)


def validate_module_spec(spec):
    """
    Validate that the spec is valid.

    Raise ValidationError otherwise.

    "Valid" means:

    * `spec` adheres to `server/models/module_spec_schema.yaml`
    * `spec.parameters[*].id_name` are unique
    * `spec.parameters[*].menu_items` or `.radio_items` are present if needed
    * `spec.parameters[*].visible_if[*].id_name` are valid
    """
    # No need to do i18n on these errors: they're only for admins. Good thing,
    # too -- most of the error messages come from jsonschema, and there are
    # _plenty_ of potential messages there.
    messages = []

    for err in _validator.iter_errors(spec):
        messages.append(err.message)
    if messages:
        # Don't bother validating the rest. The rest of this method assumes
        # the schema is valid.
        raise ValidationError(messages)

    param_id_names = set()
    for param in spec['parameters']:
        id_name = param['id_name']

        if id_name in param_id_names:
            messages.append(f"Param '{id_name}' appears twice")
        else:
            param_id_names.add(id_name)

        if param['type'] == 'menu' and not param.get('menu_items', ''):
            messages.append(f"Param '{id_name}' needs menu_items")
        if param['type'] == 'radio' and not param.get('radio_items', ''):
            messages.append(f"Param '{id_name}' needs radio_items")

    # Now that param_id_names is full, loop again to check visible_if refs
    for param in spec['parameters']:
        try:
            visible_if = param['visible_if']
        except KeyError:
            continue

        if visible_if['id_name'] not in param_id_names:
            param_id_name = param['id_name']
            ref_id_name = visible_if['id_name']
            messages.append(
                f"Param '{param_id_name}' has visible_if "
                f"id_name '{ref_id_name}', which does not exist",
            )

    if messages:
        raise ValidationError(messages)


class ModuleVersionManager(models.Manager):
    def latest(self, module_id_name):
        try:
            return (
                self.get_queryset()
                .filter(module__id_name=module_id_name)
                .order_by('-last_update_time')
            )[0]
        except IndexError:
            raise ModuleVersion.DoesNotExist


class ModuleVersion(models.Model):
    class Meta:
        ordering = ['last_update_time']

    objects = ModuleVersionManager()

    # which version of this module are we currently at (based on the source)?
    source_version_hash = models.CharField('source_version_hash',
                                           max_length=200, default='1.0')

    # time this module was last updated
    # null for the core (read internal) modules.
    last_update_time = models.DateTimeField('last_update_time', null=True,
                                            auto_now_add=True)

    module = models.ForeignKey(
        'Module',
        related_name='module_versions',
        on_delete=models.CASCADE
    )

    # Does this module provide an html file for additional output?
    html_output = models.BooleanField('html_output', default=False)

    spec = JSONField('spec', null=True, validators=[validate_module_spec])

    def save(self, *args, **kwargs):
        # TODO nix html_output field and nix this (once spec is NOT NULL)
        self.html_output = self.spec.get('html_output', False)
        super().save(*args, **kwargs)

    @staticmethod
    def create_or_replace_from_spec(spec, *, source_version_hash='',
                                    js_module='') -> 'ModuleVersion':
        validate_module_spec(spec)  # raises ValidationError
        id_name = spec['id_name']
        from .ParameterSpec import ParameterSpec

        with transaction.atomic():
            module, _ = Module.objects.update_or_create(
                id_name=id_name,
                defaults={
                    'name': spec.get('name', ''),
                    'category': spec.get('category', ''),
                    'dispatch': '',  # TODO nix (unused) dispatch
                    'source': spec.get('source', ''),
                    'description': spec.get('description', ''),
                    # TODO (unused) author
                    'author': spec.get('author', 'Workbench'),
                    'link': spec.get('link', ''),
                    'icon': spec.get('icon', 'url'),
                    'loads_data': spec.get('loads_data', False),
                    'has_zen_mode': spec.get('has_zen_mode', False),
                    'help_url': spec.get('help_url', ''),
                    'row_action_menu_entry_title': spec.get(
                        'row_action_menu_entry_title',
                        ''
                    ),
                    'js_module': js_module
                }
            )

            module_version, _ = module.module_versions.update_or_create(
                module=module,
                source_version_hash=source_version_hash,
                defaults={
                    'spec': spec,
                }
            )

            # Wipe parameter_specs and start again
            module_version.parameter_specs.all().delete()

            # Build parameter_specs
            #
            # TODO do not write parameter_specs to the database. It's
            # convoluted. Use helpers atop module_version.spec['parameters']
            # (once module_version.spec IS NOT NULL)
            for i, param in enumerate(spec['parameters']):
                param_spec = ParameterSpec(
                    module_version=module_version,
                    order=i,
                    id_name=param['id_name'],
                    name=param.get('name', ''),
                    type=param['type'],
                    items=param.get('menu_items',
                                    param.get('radio_items', '')),
                    multiline=param.get('multiline', False),
                    placeholder=param.get('placeholder', ''),
                )
                # now that param_spec.type is set, convert default to str
                param_spec.def_value = param_spec.value_to_str(
                    param.get('default', '')
                )
                if 'visible_if' in param:
                    param_spec.visible_if = json.dumps(param['visible_if'])
                param_spec.save()

            return module_version

    # Shortcut properties so we can duck-type ModuleVersion and make it look
    # exactly like a Module.
    #
    # Really, this is inverted: `Module` should have no properties (or, heck,
    # not exist at all). `ModuleVersion` is the only user-visible thing.
    @property
    def id_name(self):
        if not self.spec:  # TODO nix this case
            return self.module.id_name

        return self.spec['id_name']

    @property
    def name(self):
        if not self.spec:  # TODO nix this case
            return self.module.name

        return self.spec['name']

    @property
    def category(self):
        if not self.spec:  # TODO nix this case
            return self.module.category

        return self.spec['category']

    @property
    def description(self):
        if not self.spec:  # TODO nix this case
            return self.module.description

        return self.spec.get('description', '')

    @property
    def author(self):
        if not self.spec:  # TODO nix this case
            return self.module.author

        return self.spec.get('author', 'Workbench')

    @property
    def link(self):
        if not self.spec:  # TODO nix this case
            return self.module.link

        return self.spec.get('link', '')

    @property
    def icon(self):
        if not self.spec:  # TODO nix this case
            return self.module.icon

        return self.spec.get('icon', 'url')

    @property
    def loads_data(self):
        if not self.spec:  # TODO nix this case
            return self.module.loads_data

        return self.spec.get('loads_data', False)

    @property
    def has_zen_mode(self):
        if not self.spec:  # TODO nix this case
            return self.module.has_zen_mode

        return self.spec.get('has_zen_mode', False)

    @property
    def help_url(self):
        if not self.spec:  # TODO nix this case
            return self.module.help_url

        return self.spec.get('help_url', '')

    @property
    def row_action_menu_entry_title(self):
        if not self.spec:  # TODO nix this case
            return self.module.row_action_menu_entry_title

        return self.spec.get('row_action_menu_entry_title', '')

    @property
    def js_module(self):
        # TODO migrate module.js_module to module_version.js_module, then nix
        # this getter entirely
        return self.module.js_module

    def get_default_params(self):
        # TODO use self.spec instead of table data
        ret = {}
        for spec in self.parameter_specs.all():
            if spec.type != 'secret':
                ret[spec.id_name] = spec.str_to_value(spec.def_value)
        return ret

    def __str__(self):
        return '%s#%s' % (self.id_name, self.source_version_hash)