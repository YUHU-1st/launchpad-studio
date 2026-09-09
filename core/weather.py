from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WMO_TEXT = {
    0:"晴朗", 1:"大部晴朗", 2:"局部多云", 3:"阴天", 45:"有雾", 48:"雾凇",
    51:"小毛毛雨", 53:"毛毛雨", 55:"强毛毛雨", 61:"小雨", 63:"中雨", 65:"大雨",
    71:"小雪", 73:"中雪", 75:"大雪", 80:"阵雨", 81:"较强阵雨", 82:"强阵雨",
    95:"雷暴", 96:"雷暴伴冰雹", 99:"强雷暴伴冰雹",
}


class WeatherService:
    def __init__(self):
        self.cache={}

    @staticmethod
    def _json(url):
        request=Request(url,headers={"User-Agent":"LaunchpadStudio/1.0"})
        with urlopen(request,timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch(self,city):
        city=city.strip()
        cached=self.cache.get(city.casefold())
        if cached and time.time()-cached[0]<600:return cached[1]
        geo=self._json("https://geocoding-api.open-meteo.com/v1/search?"+urlencode({"name":city,"count":1,"language":"zh","format":"json"}))
        results=geo.get("results") or []
        if not results:raise ValueError(f"找不到城市：{city}")
        place=results[0]
        data=self._json("https://api.open-meteo.com/v1/forecast?"+urlencode({
            "latitude":place["latitude"],"longitude":place["longitude"],
            "current":"temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily":"temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone":"auto","forecast_days":3,
        }))
        current=data["current"]; daily=data["daily"]
        result={"place":f"{place.get('name',city)} · {place.get('admin1') or place.get('country','')}",
                "temperature":float(current["temperature_2m"]),"apparent":float(current["apparent_temperature"]),
                "humidity":int(current["relative_humidity_2m"]),"wind":float(current["wind_speed_10m"]),
                "code":int(current["weather_code"]),"description":WMO_TEXT.get(int(current["weather_code"]),"未知天气"),
                "high":float(daily["temperature_2m_max"][0]),"low":float(daily["temperature_2m_min"][0]),
                "rain":int(daily["precipitation_probability_max"][0] or 0)}
        self.cache[city.casefold()]=(time.time(),result)
        return result
