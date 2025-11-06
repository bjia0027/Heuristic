#pragma once
#include "model_26.h"

class UIComponent26 {
public:
    UIComponent26();
    void render();
    void setModel(Model26* model);
private:
    Model26* model_;
};
