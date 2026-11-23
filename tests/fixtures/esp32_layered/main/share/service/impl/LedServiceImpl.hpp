#pragma once
#include "LedService.hpp"
#include "RgbLed.hpp"
class LedServiceImpl : public LedService { public: int start() override; };
