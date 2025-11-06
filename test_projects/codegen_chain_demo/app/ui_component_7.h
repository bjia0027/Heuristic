#pragma once
#include "model_7.h"

class UIComponent7 {
public:
    UIComponent7();
    void render();
    void setModel(Model7* model);
private:
    Model7* model_;
};
