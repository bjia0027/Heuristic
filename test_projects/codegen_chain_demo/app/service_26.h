#pragma once
#include <functional>
#include <vector>

class Service26 {
public:
    Service26();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
