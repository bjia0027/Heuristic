#pragma once
#include "model_19.h"

class UIComponent19 {
public:
    UIComponent19();
    void render();
    void setModel(Model19* model);
private:
    Model19* model_;
};
