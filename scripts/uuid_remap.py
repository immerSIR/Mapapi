"""Transforme un dump `dumpdata` (PK entières) en dump à PK UUID, en remappant
toutes les clés étrangères / M2M de façon cohérente.

Usage (dans le conteneur, Django configuré) :
    python scripts/uuid_remap.py /tmp/mapapi_backup.json /tmp/mapapi_backup_uuid.json

Principe : on génère un UUID déterministe par (model, ancien_pk), puis on réécrit
chaque pk + chaque champ FK/O2O/M2M qui pointe vers un modèle converti. Les FK
vers des modèles NON convertis (auth.Group, contenttypes…) restent inchangées.
"""
import json
import sys
import uuid

import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.apps import apps  # noqa: E402


def model_label(model):
    return f"{model._meta.app_label}.{model._meta.model_name}"


def build_relation_maps():
    """Retourne (fk_targets, m2m_targets) : {label: {field_name: target_label}}."""
    fk_targets, m2m_targets = {}, {}
    for model in apps.get_models():
        label = model_label(model)
        fks, m2ms = {}, {}
        for field in model._meta.get_fields():
            if not field.is_relation:
                continue
            if field.many_to_many and not field.auto_created:
                if field.related_model is not None:
                    m2ms[field.name] = model_label(field.related_model)
            elif (field.many_to_one or field.one_to_one) and field.concrete:
                if field.related_model is not None:
                    fks[field.name] = model_label(field.related_model)
        fk_targets[label] = fks
        m2m_targets[label] = m2ms
    return fk_targets, m2m_targets


def main(in_path, out_path):
    data = json.load(open(in_path))
    fk_targets, m2m_targets = build_relation_maps()

    # Quels modèles convertit-on ? Ceux présents dans le dump.
    converted = {obj['model'] for obj in data}

    # 1) UUID par (model, ancien_pk)
    pk_map = {}
    for obj in data:
        key = (obj['model'], str(obj['pk']))
        pk_map[key] = str(uuid.uuid4())

    def remap_ref(target_label, old_value):
        if old_value is None:
            return None
        if target_label not in converted:
            return old_value  # FK vers un modèle non converti → inchangé
        return pk_map.get((target_label, str(old_value)), old_value)

    # 2) Réécriture
    stats = {'objects': 0, 'fk_remapped': 0, 'm2m_remapped': 0, 'fk_unmapped': 0}
    for obj in data:
        label = obj['model']
        obj['pk'] = pk_map[(label, str(obj['pk']))]
        fields = obj.get('fields', {})
        for fname, target in fk_targets.get(label, {}).items():
            if fname in fields and fields[fname] is not None:
                new = remap_ref(target, fields[fname])
                if target in converted and new == fields[fname]:
                    stats['fk_unmapped'] += 1  # référence manquante (à signaler)
                fields[fname] = new
                stats['fk_remapped'] += 1
        for fname, target in m2m_targets.get(label, {}).items():
            if fname in fields and isinstance(fields[fname], list):
                fields[fname] = [remap_ref(target, v) for v in fields[fname]]
                stats['m2m_remapped'] += 1
        stats['objects'] += 1

    json.dump(data, open(out_path, 'w'))
    print('REMAP OK ->', out_path)
    print('stats:', stats)
    print('models converted:', len(converted))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
