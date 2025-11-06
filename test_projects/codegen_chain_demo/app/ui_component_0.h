#pragma once
#include "model_0.h"

class UIComponent0 {
public:
    UIComponent0();
    void render();
    void setModel(Model0* model);
private:
    Model0* model_;
};
