from typing import Union
import time
import pandas as pd
import requests_cache
import sdmxthon

from .sdmx_parser import _parse_data_sdmx_json

# 5 minutes
_CACHE_EXPIRE_AFTER_N_SECONDS = 5 * 60



def  _component_to_dict(component_id, component,lang) -> dict:
    ret = {"id": component_id, "name": str(component.concept_identity.name)}

    if component.local_representation is not None and component.local_representation.codelist is not None:
        cl_items = component.local_representation.codelist.items
        ret["codes"]=[]
        for code in cl_items:
            if isinstance(cl_items[code].name, dict):
                ret["codes"].append({"id":code, "name":cl_items[code].name[lang]["content"]})
            else:
                ret["codes"].append({"id":code, "name":cl_items[code].name})
            if cl_items[code].parent is not None:
                if isinstance(cl_items[code].parent,str):
                    ret["codes"][-1]["parent"]=cl_items[code].parent
                else:
                    ret["codes"][-1]["parent"]=cl_items[code].parent.id


    return ret
    


class SDMX_DataAccess:
    _DQ_ALL = "all"

    def __init__(self, sdmx_endpoint_url: str) -> None:
        if sdmx_endpoint_url.endswith("/"):
            self.sdmx_endpoint_url = sdmx_endpoint_url
        else:
            self.sdmx_endpoint_url = sdmx_endpoint_url + "/"

    # returns true if the data query filter (AFG..) is empty (query for all)
    def _data_query_is_all(self, dq) -> bool:
        if dq is None:
            return True
        if isinstance(dq, str):
            if dq.strip() == "":
                return True
            return False
        for v in dq.values():
            if len(v) > 0:
                return False
        return True


    def get_dataflow_info(self, agency: str, id: str, ver: str, lang: str, print_stats=False )->dict:
        
        ret ={"name":"", "dsd":{}}
        # API call params
        params = "?detail=full&references=all"
        # build the API call
        url = f"{self.sdmx_endpoint_url}dataflow/{agency}/{id}/{ver}/{params}"
        df_id = f"{agency}:{id}({ver})"

        sdmx_msg = None

        try:
            sdmx_msg = sdmxthon.read_sdmx(url)
        except:
            raise (                ConnectionError(                    "Error downloading "+ url                )            )
        
        df_content = sdmx_msg.content["Dataflows"][df_id]
        ret["name"] = df_content.name

        ret["dsd"]["dims"] = []
        sdmx_dims = df_content.structure.content["dimensions"]

        for dim_id in sdmx_dims:
             ret["dsd"]["dims"].append(_component_to_dict(dim_id,sdmx_dims[dim_id],lang))
             if dim_id =="TIME_PERIOD":
                 ret["dsd"]["dims"][-1]["is_time"]=True
             else:
                 ret["dsd"]["dims"][-1]["is_time"]=False

        ret["dsd"]["attribs"] = []
        sdmx_attribs = df_content.structure.content["attributes"]
        for attr_id in sdmx_attribs:
             ret["dsd"]["attribs"].append(_component_to_dict(attr_id,sdmx_attribs[attr_id], lang))

        ret["dsd"]["measures"] = []
        sdmx_measure = df_content.structure.content["measure"]
        ret["dsd"]["measures"].append(_component_to_dict(sdmx_measure.id, sdmx_measure, lang))

        
        return ret




    

    def get_data(
        self,
        agency: str,
        id: str,
        ver: str,
        dq: Union[dict, str] = None,
        startperiod=None,
        endperiod=None,
        lastnobs=False,
        print_stats=False,
        labels="both",
    ) -> pd.DataFrame:
        # API call params
        params = {"format": "sdmx-json"}
        # build the API call
        url = f"{self.sdmx_endpoint_url}data/{agency},{id},{ver}/"
        # Data query can be a string: AFG.._T or a dict
        if self._data_query_is_all(dq):
            dq_to_send = self._DQ_ALL
        else:
            if isinstance(dq, str):
                dq_to_send = dq
            else:
                dq_to_send = []
                for v in dq.values():
                    dq_to_send.append("+".join(v))
                dq_to_send = ".".join(dq_to_send)

        url = url + dq_to_send

        if startperiod is not None:
            params["startPeriod"] = startperiod
        if endperiod is not None:
            params["endPeriod"] = endperiod
        if lastnobs:
            params["startPeriod"] = startperiod if startperiod is not None else 1900
            params["lastnobservations"] = 1

        start_time = time.time()

        # add some caching
        session = requests_cache.CachedSession(
            "data_cache", expire_after=_CACHE_EXPIRE_AFTER_N_SECONDS
        )

        r = session.get(url, params=params)

        if r.ok:
            jdata = r.json()
        else:
            raise (
                ConnectionError(
                    "Error downloading "
                    + url
                    + " status code: "
                    + str(r.status_code)
                    + r.raise_for_status()
                )
            )
        if print_stats:
            print("get_data download: %s seconds" % (time.time() - start_time))

        start_time = time.time()
        ret = _parse_data_sdmx_json(jdata, labels)
        if print_stats:
            print("get_data (manual) parsing: %s seconds" % (time.time() - start_time))
            print(r.request.url)
            print(f"{str(len(ret))} data points downloaded")

        return ret
