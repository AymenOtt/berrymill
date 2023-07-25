"""
Find out local repos of the current distro.
"""
from __future__ import annotations
import os
import re
from abc import ABCMeta, abstractmethod
from typing import List, Dict, Tuple, Any


class Repodata:
    def __init__(self) -> None:
        self.type: str = ""
        self.components: Tuple[str] = tuple()  # Not mandatory
        self.url: str = ""
        self.trusted: bool = False
        self.name: str = ""
        self.attrs: Dict[str, str] = {}
        self.is_flat: bool = False

    @property
    def is_valid(self) -> bool:
        return "" not in [self.type, self.url, self.name]

    def __repr__(self) -> str:
        d:List[str] = [f"<Repo: {self.name}", f"Type: {self.type}"]
        if self.url:
            d.append(f"URL: {self.url}")
        if self.attrs:
            d.append(f"Attributes: {self.attrs}")
        d.append(self.trusted and "Trusted" or "Untrusted")
        if self.components:
            c:str = ", ".join(self.components)
            d.append(f"Components: {c}")
        d.append("Format: " + (self.is_flat and "flat" or "standard"))

        return ", ".join(d)

    def merge(self, repo:Repodata):
        """
        Merge the repodata, as long as the URL is the same
        """
        if self.url != repo.url:
            raise Exception(f"Unable to merge {repo.url}")

        self.components = tuple(sorted(set(list(self.components) + list(repo.components))))
        if not repo.trusted:
            self.trusted = False
        self.attrs.update(repo.attrs)

    def to_json(self) -> Dict[str, Any]:
        """
        Serialise the repodata to the JSON format
        """
        data = {}
        for arch in self.attrs.get("arch", "amd64").split(","):
            if data.get(arch) is None:
                data[arch] = {}
            data[arch][self.name] = {
                "url": self.url,
                "type": self.type,
                "name": self.name,
                "components": ",".join(self.components) or "/",  # "/" for flat format
            }

        return data


class BaseRepofind(metaclass=ABCMeta):
    """
    Repofind mixin
    """

    @abstractmethod
    def get_repos(self) -> List[str]:
        """
        Return list of repositories
        """


class DebianRepofind(BaseRepofind):
    """
    Debian repositories
    """
    def __init__(self) -> None:
        super().__init__()
        self._attrfix = re.compile("\\s+")

    def _parse_repo(self, repodata:str) -> Repodata:
        cp_repodata = repodata
        r = Repodata()

        if not repodata.startswith("deb "):
            # invalid
            return r
        else:
            r.type = "apt-deb"

        repodata = repodata[3:].strip()
        if repodata.startswith("[") and "]" in repodata:
            for attrset in self._attrfix.sub(" ", repodata[1:].split("]")[0].strip()).split(" "):
                kw = attrset.split("=", 1)
                r.attrs[kw[0]] = kw[1]
            repodata = repodata.split("]")[1].strip()

        r.url = repodata.split(" ")[0]
        repodata = repodata[len(r.url):].strip()
        if repodata == "/":
            r.is_flat = True
            r.name = "_".join(r.url.split("://")[-1].split("/")).replace(".", "_").lower().strip("_").replace(":", "")
        else:
            nc:List[str] = repodata.split(" ")
            if len(nc) < 2:
                raise Exception("Unknown repository format: ", cp_repodata)
            r.name = nc.pop(0)
            r.components = tuple(nc)

        return r

    def _parse_repofile(self, repofile:str) -> List[Repodata]:
        """
        Grab all repos, defined in a given repofile
        """
        repos:List[Repodata] = []

        with open(repofile) as rf:
            for l in rf.readlines():
                l = l.strip()
                if l.startswith("#"):
                    l = ""
                if not l: continue

                r = self._parse_repo(l)
                if r.is_valid:
                    repos.append(r)

        return repos

    def get_repos(self) -> List[Repodata]:
        """
        Return all local repositories, flatteing them.
        """
        repofiles:List[str] = ["/etc/apt/sources.list"]
        ddir = "/etc/apt/sources.list.d"
        for rf in os.listdir(ddir):
            if rf.endswith(".list"):  # cut off the possible junk, backups, copies etc
                repofiles.append(os.path.join(ddir, rf))

        repos:List[Repodata] = []
        ridx:Dict[str, List[Repodata]] = {}

        # Find out same URL, different components (e.g. url->main, url->universe etc)
        for rf in repofiles:
            for r in self._parse_repofile(rf):
                if not ridx.get(r.url):
                    ridx[r.url] = []
                ridx[r.url].append(r)

        # Flatten repos, those has the same URL (merge their data)
        for v in ridx.values():
            if not v: continue
            if len(v) > 1:
                r:Repodata|None = None
                for _r in v:
                    if r is None:
                        r = _r
                    else:
                        r.merge(_r)
                if r is not None:
                    repos.append(r)
            else:
                repos += v

        return repos