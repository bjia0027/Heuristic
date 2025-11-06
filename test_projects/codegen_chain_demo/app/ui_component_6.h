#pragma once
#include "model_6.h"

class UIComponent6 {
public:
    UIComponent6();
    void render();
    void setModel(Model6* model);
private:
    Model6* model_;
};
