from __future__ import annotations

import ipaddress
from typing import Optional, Union, List, Dict
from enum import Enum

from pydantic import (
        BaseModel,
        model_validator,
        field_serializer,
        field_validator,
        )


class NetworkRecord(BaseModel):
    name: str
    subnet: ipaddress.IPv6Network
    hosts: dict[str, HostRecord]

    # @property
    # def name(self):
    #     return self.subnet.compressed.replace(":", "-").replace("/", "x")
    #
    @field_serializer("subnet")
    def serialize_subnet(self, subnet: ipaddress.IPv6Network) -> str:
        return str(subnet)

    @field_validator("subnet", mode="before")
    @classmethod
    def deserialize_subnet(cls, value):
        if isinstance(value, str):
            return ipaddress.IPv6Network(value)
        return value


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


class CertificateRequest(BaseModel):
    network_name: str
    host_name: str
    pub_key: str

class AppStoreMeshPrivileges(Enum):
    #TODO: finish implementing this properly after discussing with team
    EditStore = 0
    ViewFullStore = 1
    ViewLimited = 2

class ParseError(Exception):
    pass
#TODO: replace with config I/O instead of matching brackets
# + Dataclasses
class Image:
    def __init__(self) -> None:
       self.ubuntu : str = ""
       self.python : str = ""
       self.nginx : str = ""
       self.command_map : Dict[str, str]
       self.key : str = ""
       self.Command_Map = {
            self.ubuntu : "ubuntu:22.04",
            self.python : "python:3.11",
            self.nginx : "nginx:alpine"} 

    def parse(self, image: str) -> ParseError | None:
        match image:
            case "ubuntu":
                self.key = self.ubuntu
            case "python":
                self.key = self.python
            case "nginx":
                self.key = self.nginx
            case _:
                return ParseError("Incorrect Arg")

    def fetch_command(self) -> str:
        return self.Command_Map.get(self.key, "could not fetch command") 

class Container(BaseModel):
    application_list : List[str]
    version : str
    nusers : int

class AppStoreSpinupReport(BaseModel):
    image_path : str
    container_list : List[Container]

class AppStoreSpinupRequest(BaseModel):
    image_path : str
    federated : bool #for mutual trust feature later
    privilege : AppStoreMeshPrivileges

class HostRequest(BaseModel):
    name: str
    network_name: str
    is_lighthouse: bool
    public_ip: Optional[Union[ipaddress.IPv6Address, ipaddress.IPv4Address]] = None

    @model_validator(mode="after")
    def validate_lighthouse_ip(self):
        if self.is_lighthouse and self.public_ip is None:
            raise ValueError("Lighthouses must have a public_ip")
        if not self.is_lighthouse and self.public_ip is not None:
            raise ValueError("Non-lighthouses must not have a public_ip")
        return self
