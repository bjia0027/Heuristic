#pragma once
#include "service_14.h"
#include "model_14.h"
#include <memory>

class Controller14 {
public:
    Controller14();
    void initialize();
    void run();
private:
    std::unique_ptr<Service14> service_;
    std::shared_ptr<Model14> model_;
};
