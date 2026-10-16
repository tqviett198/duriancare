from django.contrib import admin

from .models import Farm, FarmMembership, PlantingCode, Plot, PlotSeason, Season

admin.site.register([Farm, FarmMembership, PlantingCode, Plot, Season, PlotSeason])
