from __future__ import annotations

import ipaddress
import secrets
from enum import Enum
from ipaddress import IPv6Address
from pathlib import Path
from typing import Optional, Union, List

from pydantic import (
        BaseModel,
        model_validator,
        field_serializer,
        field_validator,
        )


class AddAAAARequest(BaseModel):
    name: str
    ip: str

def _random_host_ip(prefix) -> IPv6Address:
    return IPv6Address(
            int(prefix.network_address) | secrets.randbits(64)
            )



#TODO: test_this (DONE!!): both serializers and get_ip_address
class NetworkRecord(BaseModel):
    name: str
    subnet: ipaddress.IPv6Network
    hosts: dict[str, HostRecord]
    apps: dict[str, AppRecord]
    dns: bool

    @field_serializer("subnet")
    def serialize_subnet(self, subnet: ipaddress.IPv6Network) -> str:
        return str(subnet)

    @field_validator("subnet", mode="before")
    @classmethod
    def deserialize_subnet(cls, value):
        if isinstance(value, str):
            return ipaddress.IPv6Network(value)
        return value

    def get_ip_address(self) -> IPv6Address:
        if len(self.hosts) == 0:
            # First host gets [subnet]::1, the rest gets random ips
            return next(self.subnet.hosts())
        else:
            return _random_host_ip(self.subnet)

    def get_cep(self) -> HostRecord:
        for host_record in self.hosts.values():
            if int(host_record.ip) - int(self.subnet.network_address) == 1:
                return host_record

class NetworkStore(BaseModel):
    networks: dict[str, NetworkRecord]


class HostRecord(BaseModel):
    name: str
    ip: ipaddress.IPv6Address
    groups: list[str]
    is_lighthouse: bool
    public_key: Optional[str] = None
    public_ip: Optional[Union[ipaddress.IPv6Address, ipaddress.IPv4Address]] = None

    @model_validator(mode="after")
    def validate_lighthouse_ip(self):
        if self.is_lighthouse and self.public_ip is None:
            raise ValueError("Lighthouses must have a public_ip")
        if not self.is_lighthouse and self.public_ip is not None:
            raise ValueError("Non-lighthouses must not have a public_ip")
        return self

    @field_serializer("ip")
    def serialize_ip(self, ip: ipaddress.IPv6Address) -> str:
        return str(ip) if ip else ip

    @field_validator("ip", mode="before")
    @classmethod
    def deserialize_ip(cls, value):
        if isinstance(value, str):
            return ipaddress.ip_address(value)
        return value

    @field_serializer("public_ip")
    def serialize_public_ip(self, public_ip: Union[ipaddress.IPv6Address, ipaddress.IPv4Address]) -> str:
        return str(public_ip) if public_ip else public_ip

    @field_validator("public_ip", mode="before")
    @classmethod
    def deserialize_public_ip(cls, value):
        if isinstance(value, str):
            return ipaddress.ip_address(value)
        return value

class AppRecord(BaseModel):
    name: str
    ip: ipaddress.IPv6Address

    @field_serializer("ip")
    def serialize_ip(self, ip: ipaddress.IPv6Address) -> str:
        return str(ip) if ip else ip

    @field_validator("ip", mode="before")
    @classmethod
    def deserialize_ip(cls, value):
        if isinstance(value, str):
            return ipaddress.ip_address(value)
        return value

class CertificateRequest(BaseModel):
    network_name: str
    host_name: str
    pub_key: str


class SignedCertificate(BaseModel):
    ca_cert_path: Path
    ca_key_path: Path
    cert_path: Path


class HostRequest(BaseModel):
    name: str
    network_name: str
    is_lighthouse: bool
    public_ip: Optional[Union[ipaddress.IPv6Address, ipaddress.IPv4Address]] = None
    add_dns_record: Optional[bool] = True

    @model_validator(mode="after")
    def validate_lighthouse_ip(self):
        if self.is_lighthouse and self.public_ip is None:
            raise ValueError("Lighthouses must have a public_ip")
        if not self.is_lighthouse and self.public_ip is not None:
            raise ValueError("Non-lighthouses must not have a public_ip")
        return self

LighthouseResponse = dict[str, str]

class Container(BaseModel):
    version: int
    nusers: int
    already_up: bool


class AppStoreSpinupReport(BaseModel):
    image_path: str
    container_list: List[Container]


class PoolRecord(BaseModel):
    name: str
    path: str
    created_at: str


class VolumeRecord(BaseModel):
    name: str
    pool_name: str
    host_path: str
    created_at: str


class StorageStore(BaseModel):
    pools: dict[str, PoolRecord] = {}
    volumes: dict[str, VolumeRecord] = {}


class AppStoreMeshPrivileges(Enum):
    #TODO: finish implementing this properly after discussing with team
    EditStore = 0
    ViewFullStore = 1
    ViewLimited = 2
