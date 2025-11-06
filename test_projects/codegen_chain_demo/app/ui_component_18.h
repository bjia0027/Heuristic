#pragma once
#include "model_18.h"

class UIComponent18 {
public:
    UIComponent18();
    void render();
    void setModel(Model18* model);
private:
    Model18* model_;
};
