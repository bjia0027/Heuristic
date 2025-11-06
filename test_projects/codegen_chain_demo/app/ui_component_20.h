#pragma once
#include "model_20.h"

class UIComponent20 {
public:
    UIComponent20();
    void render();
    void setModel(Model20* model);
private:
    Model20* model_;
};
