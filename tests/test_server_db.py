"""
Tests for load_db and save_db.

TODO reference: server/utils.py:14,24 – "existing and non existing dbs need to be identified"

Covers:
- load_db when DB file does not exist → empty NetworkStore
- load_db when DB file exists → correct NetworkStore reconstructed
- save_db writes JSON that load_db can re-read exactly
- save_db overwrites; subsequent load_db sees the new state
- AppRecord roundtrips (ip serializer/deserializer) through the DB
- Pre-feature db.json files without an "apps" key still load
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest

from cep.datamodels import AppRecord, HostRecord, NetworkRecord, NetworkStore
from cep.server.utils import load_db, save_db


class TestLoadDb:
    def test_returns_empty_store_when_file_missing(self, server_dir):
        store = load_db()
        assert store.networks == {}, "Expected empty networks dict when DB file is absent"

    def test_returns_correct_store_when_file_exists(self, server_dir):
        net = NetworkRecord(
            name="mynet",
            subnet=ipaddress.IPv6Network("fd00::/64"),
            hosts={},
            dns=False,
        )
        # Write the file by hand so we are testing load_db, not save_db
        db_path = server_dir / "db.json"
        db_path.write_text(
            json.dumps({"networks": {"mynet": json.loads(net.model_dump_json())}})
        )

        store = load_db()
        assert "mynet" in store.networks
        assert store.networks["mynet"].name == "mynet"
        assert store.networks["mynet"].subnet == ipaddress.IPv6Network("fd00::/64")

    def test_reconstructs_host_records(self, server_dir):
        host = HostRecord(
            name="lh",
            ip=ipaddress.ip_address("fd00::1"),
            groups=[],
            is_lighthouse=True,
            public_ip=ipaddress.ip_address("1.2.3.4"),
        )
        net = NetworkRecord(
            name="mynet",
            subnet=ipaddress.IPv6Network("fd00::/64"),
            hosts={"lh": host},
            dns=False,
        )
        db_path = server_dir / "db.json"
        store_dict = NetworkStore(networks={"mynet": net}).model_dump()
        db_path.write_text(json.dumps(store_dict))

        store = load_db()
        assert "lh" in store.networks["mynet"].hosts
        lh = store.networks["mynet"].hosts["lh"]
        assert lh.is_lighthouse is True
        assert str(lh.public_ip) == "1.2.3.4"


class TestSaveDb:
    def test_creates_file_on_first_save(self, server_dir):
        db_path = server_dir / "db.json"
        assert not db_path.exists()

        save_db(NetworkStore(networks={}))
        assert db_path.exists()

    def test_saved_file_is_valid_json(self, server_dir):
        save_db(NetworkStore(networks={}))
        db_path = server_dir / "db.json"
        data = json.loads(db_path.read_text())
        assert "networks" in data

    def test_saved_content_matches_input(self, server_dir):
        net = NetworkRecord(
            name="mynet",
            subnet=ipaddress.IPv6Network("fd00::/64"),
            hosts={},
            dns=True,
        )
        save_db(NetworkStore(networks={"mynet": net}))
        reloaded = load_db()
        assert "mynet" in reloaded.networks
        assert reloaded.networks["mynet"].dns is True
        assert reloaded.networks["mynet"].subnet == net.subnet

    def test_overwrite_removes_old_networks(self, server_dir):
        net_a = NetworkRecord(name="a", subnet="fda0::/64", hosts={}, dns=False)
        net_b = NetworkRecord(name="b", subnet="fdb0::/64", hosts={}, dns=False)

        save_db(NetworkStore(networks={"a": net_a}))
        save_db(NetworkStore(networks={"b": net_b}))  # overwrite

        final = load_db()
        assert "a" not in final.networks
        assert "b" in final.networks


class TestAppRecordPersistence:
    def test_reconstructs_app_records(self, server_dir):
        net = NetworkRecord(
            name="mynet",
            subnet=ipaddress.IPv6Network("fd00::/64"),
            hosts={},
            apps={"redis": AppRecord(name="redis", ip=ipaddress.ip_address("fd00::1"))},
            dns=False,
        )
        db_path = server_dir / "db.json"
        db_path.write_text(json.dumps(NetworkStore(networks={"mynet": net}).model_dump()))

        store = load_db()

        redis_record = store.networks["mynet"].apps["redis"]
        assert isinstance(redis_record, AppRecord)
        assert redis_record.name == "redis"
        assert redis_record.ip == ipaddress.ip_address("fd00::1")

    def test_app_record_ip_survives_dump_roundtrip(self):
        app = AppRecord(name="redis", ip=ipaddress.ip_address("fd00::1"))

        dumped = app.model_dump()
        restored = AppRecord.model_validate(dumped)

        assert isinstance(dumped["ip"], str)
        assert dumped["ip"] == "fd00::1"
        assert restored.ip == app.ip

    def test_apps_default_to_empty_when_missing_from_db(self, server_dir):
        """db.json files written before the apps field existed must still load."""
        db_path = server_dir / "db.json"
        db_path.write_text(
            json.dumps(
                {
                    "networks": {
                        "mynet": {
                            "name": "mynet",
                            "subnet": "fd00::/64",
                            "hosts": {},
                            "dns": False,
                        }
                    }
                }
            )
        )

        store = load_db()

        assert store.networks["mynet"].apps == {}
